# JobFit Engineering Patterns

A reference card for *how* this codebase is built, not what it does. Patterns are extracted from
the actual code; file paths point at canonical examples.

---

## 1. Session workflow

**`HANDOFF.md` — living state snapshot.**
- *What:* a single root file, **overwritten** each checkpoint, holding the current state in a fixed
  schema (`Updated`/`Branch` + Current State · Next Action · Why It Stopped · In-Flight · Open
  Questions · Verification Baseline).
- *Why:* any cold-start session resumes from one place; a Stop hook blocks session end when the tree
  is dirty and HANDOFF is stale (>30 min).
- *Shape:* read it at session start; overwrite it at each checkpoint; "Next Action" must be
  immediately actionable.

**`tasks/todo.md` — plan as a checklist.**
- *What:* the task list written **before** implementation; items marked `- [x]` as completed (not batched).
- *Why:* makes scope explicit and check-in-able before code is touched.

**`tasks/lessons.md` — append-only correction log.**
- *What:* one entry per correction or non-obvious discovery, in `Pattern: / Fix: / Avoid: / See:` form.
- *Why:* a pattern recurring 3+ times earns its own skill (see `RESOLVER.md` Growth Rules).

**Checkpoint triggers** (overwrite HANDOFF when any fires): task complete · wave/milestone done ·
user signals stop · unresolved blocker · context ~70% · 30+ min without an update.

**Plan-before-build.** Enter plan mode for any non-trivial task (3+ steps or architectural);
check in with the user before implementing, not during. Skill routing lives in `RESOLVER.md`
(`conventions.md` is near-default for implementation tasks).

---

## 2. Agent architecture

**`BaseAgent` — one shape for every Claude call.** (`backend/agents/base.py`)
- *What:* a base class holding the shared async client, prompt loader, slot injector, and the single
  `_call()` that routes through cost tracking.
- *Why:* every agent gets identical cost logging, model tiering, and parsing discipline for free.
```python
class BaseAgent:
    model: str = SONNET                       # default tier; orchestrator may override per dispatch
    def _load_prompt(self, name): return (PROMPTS_DIR / f"{name}.md").read_text()
    def _inject(self, template, profile, jd, prior):   # fill {profile}/{jd}/{prior.<field>}
        ...
    async def _call(self, system, user):       # → tracked_call(...) → LLMCall row
        ...
```

**Prompt loading from versioned `.md` files.**
- *What:* each agent's system prompt is a file in `backend/prompts/<agent>.md`, loaded by `_load_prompt`.
- *Why:* prompts are reviewable/versioned artifacts, not string literals buried in code.

**`_inject()` vs manual `.replace()`.**
- *What:* pipeline agents that consume structured `PriorOutputs` use `_inject()`; leaf agents with
  bespoke inputs (e.g. cold-email's `contact_name`) use manual `template.replace(...)` chains.
- *Why:* `_inject` is for the shared profile/jd/prior shape; don't force odd-shaped agents into it.

**`with_tracking()` — per-request DB attach.**
- *What:* `agent.with_tracking(db, run_id=, analysis_id=)` mutates the instance to attach a session +
  correlation ids for cost logging.
- *Why:* ties each LLM call's cost row to its request. **Instantiate agents fresh per request; never
  reuse** — a stale `db`/`run_id` would silently persist.

**Model tiering (Sonnet default, Haiku for bulk).**
- *What:* agents default to `SONNET`; the orchestrator mutates `agent.model = HAIKU` at dispatch for
  cheap/bulk work (discovery scoring).
- *Why:* ~20× cost cut on bulk paths. **Never read `agent.model` as static** — its value depends on
  who dispatched it.

**Cost tracking — `tracked_call`.** (`backend/services/instrumentation.py`)
- *What:* wraps `messages.create`, writes one `LLMCall` row (tokens, `cost_usd`, latency, cache
  tokens, `run_id`/`analysis_id`); **fail-open** (a tracking error never breaks the LLM call).
- *Why:* a single DB-backed cost spine powers the `/metrics/costs/*` dashboard.

**Typed output parsing.**
- *What:* parse the response JSON, validate through the agent's Pydantic output schema, and re-raise
  any failure as a typed `AgentError`.
- *Why:* lets the orchestrator handle partial failure cleanly instead of crashing on bad JSON.
```python
try:
    return MatchScorerOutput.model_validate(_parse_json(raw))
except (json.JSONDecodeError, ValidationError, AgentError) as e:
    raise AgentError(f"match_scorer: {e}") from e
```

---

## 3. Pipeline patterns

**Phase 1 sequential → Phase 2 concurrent.** (`backend/services/orchestrator.py`)
- *What:* Phase 1 runs job_parser → match_scorer → gap_analyst in order (each feeds the next via
  `PriorOutputs`); Phase 2 runs resource_planner, then cover_letter ∥ resume_tailorer concurrently.
- *Why:* Phase 1 has data dependencies; Phase 2's two doc-writers are independent, so parallelize.
```python
prior = prior.model_copy(update={agent_name: output})       # thread results forward (Phase 1)
cl, rt = await asyncio.gather(_tracked(CoverLetterAgent, ...),
                              _tracked(ResumeTailorerAgent, ...),
                              return_exceptions=True)         # Phase 2 fan-out
```

**Per-coroutine sessions in the fan-out.**
- *What:* each concurrently-running agent opens its **own** `async with SessionLocal()`.
- *Why:* sharing one `AsyncSession` across concurrent coroutines corrupts SQLAlchemy's unit-of-work.

**Partial-success orchestration.**
- *What:* each agent runs in its own `try/except AgentError`; a failure flips `partial=True` and the
  pipeline continues; successful results are persisted in a `finally`.
- *Why:* one flaky agent shouldn't sink the whole analysis.

**SSE event protocol (fixed order).**
- *What:* `pipeline_start → agent_start → agent_done` (repeat per agent) `→ pipeline_done`;
  `pipeline_error` replaces `agent_done` on failure. `pipeline_done` is **always last**.
- *Why:* the frontend dispatcher hardcodes these names and **aborts on `pipeline_done`** — renaming
  or emitting after it is a breaking change.

**Result caching by `jd_hash`.**
- *What:* `jd_hash = sha256(f"{jd}::{profile.id}")`; a complete (`partial==False`) Analysis with that
  hash is returned without re-running agents, logged via `log_cache_hit` as a `cache_hit` LLMCall row.
- *Why:* skips re-scoring identical submissions. *Known limit:* keyed on `profile.id`, not profile
  **content** — editing the profile doesn't invalidate the cache.

**Background task vs SSE.**
- *What:* foreground/interactive work streams over **SSE** (analysis); long bulk work fires a
  **background task** and is polled.
```python
async def run_discovery(source, db) -> str:           # public entry: returns id immediately
    run = DiscoveryRun(...); db.add(run); await db.commit()
    task = asyncio.create_task(_run_discovery_task(run.id, source))
    _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)  # GC guard
    return run.id
```
- *Why:* SSE gives live per-agent progress; background+poll suits minutes-long multi-job runs.

---

## 4. Data layer conventions

**Session ownership.** (`backend/database.py`, `.claude/skills/conventions.md`)
- *What:* request-scoped work injects the session via `Depends(get_db)` (the dependency does
  commit/rollback/close); **background tasks own their own** `async with SessionLocal() as db`
  because they can't receive FastAPI DI; concurrent coroutines each get their own.
- *Why:* prevents leaked sessions and cross-coroutine unit-of-work corruption.
```python
# request-scoped
async def route(db: AsyncSession = Depends(get_db)): ...
# background task
async def _task(run_id):
    async with SessionLocal() as db: ...
```

**SQLAlchemy 2.0 async.**
- *What:* `select()`/`update()` + `await db.execute(...)` + `.scalar_one_or_none()`; ORM via
  `Mapped[...]` / `mapped_column(...)`; `async_sessionmaker(expire_on_commit=False)`.
- *Why:* the whole stack is async; expire-on-commit off so objects stay usable after commit.

**Migration convention (startup, additive, idempotent).** (`init_db()`)
- *What:* `create_all` handles fresh DBs; for existing SQLite DBs, `PRAGMA table_info(<table>)` +
  guarded `ALTER TABLE ... ADD COLUMN` adds new columns at startup.
- *Why:* no migration framework; additive column adds are safe and self-healing on boot.
```python
cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(analyses)"))).fetchall()}
if "match_score" not in cols:
    await conn.execute(text("ALTER TABLE analyses ADD COLUMN match_score INTEGER"))
```

---

## 5. API conventions

**Layering: route → service → agent → Claude.**
- *What:* route handlers call services; services call agents; agents call Claude. No layer skipping.
- *Why:* keeps HTTP, orchestration, and model concerns separable and testable.

**Always `settings.api_prefix`.**
- *What:* register every router with `prefix=settings.api_prefix`; never hardcode `/api`.
- *Why:* deployment-configurable prefix without touching route files.

**Background-job HTTP shape (POST returns id, GET polls).** (`backend/routes/discovery.py`)
- *What:* `POST /discovery/run` validates input, fires the background task, returns `{run_id}`
  immediately; `GET /discovery/runs/{id}` returns status + funnel for polling.
- *Why:* long work can't block a request; the client polls to completion.

**Error handling.**
- *What:* validate inputs and `raise HTTPException(422, ...)` **before** any DB write; auth via
  `Depends(get_current_user)` (401 when absent); tracking writes are fail-open; agent failures are
  typed (`AgentError`) and downgraded to partial results, not 500s.
- *Why:* reject bad requests cheaply; never let telemetry or one agent break the response.

---

## 6. Testing conventions

**TDD: RED → GREEN.**
- *What:* write one failing test, run it and confirm it fails for the expected reason, then write the
  minimal code to pass.
- *Why:* proves the test actually exercises the behavior.

**Naming.** `test_<unit>_<behavior>` — e.g. `test_feed_dedupes_to_latest_analysis`,
`test_resource_planner_malformed`. The name states the asserted behavior.

**What gets mocked.**
- *What:* patch `Agent.run` / `BaseAgent._call` with `AsyncMock` (no real Claude calls); use an
  in-memory SQLite engine fixture (`create_all`); `conftest` provides `app_client` (auth overridden)
  and `unauthenticated_client` (for 401 tests). Fail-open paths are tested with a `bad_db` mock.
- *Why:* fast, deterministic, no network or API key.
```python
with patch.object(ResourcePlannerAgent, "_call", new=AsyncMock(side_effect=[...])):
    result = await ResourcePlannerAgent().run(profile, jd, prior)
```

**Coverage + Definition of Done.**
- *What:* `make check` = fmt → lint (ruff + mypy + pydantic→TS schema-drift) → `pytest --cov-fail-under=70`.
- *Why:* a task isn't done until `make check` passes; every new agent needs a schema test and every
  new route a happy-path + auth test.

---

## 7. Frontend conventions

**Polling loop with terminal-state exit + cap.** (`frontend/src/pages/Discover.tsx`)
- *What:* `setInterval` (3 s) on an `activeRunId`, fetching run status; clears on a terminal status;
  an attempts cap (≈200 = 10 min) trips a `timedOut` state with a manual Refresh.
- *Why:* surfaces background-job progress without holding a connection; the cap stops infinite polling
  on a wedged run.

**SSE consumption.** (`frontend/src/api/client.ts`)
- *What:* `_streamSSE` reads `event:`/`data:` frames, switches on the event name to typed callbacks,
  and `controller.abort()`s on `pipeline_done`.
- *Why:* one dispatcher for both analyse + generate streams; callbacks keep components declarative.

**Optimistic update with revert.** (`JobCard`)
- *What:* set local state immediately, fire the request, **revert on error**.
- *Why:* instant UI feedback without waiting on the round trip.
```ts
setSaved(next);
api.saveJob(id).then(() => onToggleSave?.(id, next)).catch(() => setSaved(!next));  // revert
```

**Async-UI state machine.**
- *What:* components model async flows as an explicit phase enum rather than scattered booleans.
  - Analyse: `idle → evaluating → evaluated → generating`
  - Discover run: `idle → running → complete | failed | timedOut`
- *Why:* a single state value makes the UI's legal transitions obvious and prevents impossible combos.
