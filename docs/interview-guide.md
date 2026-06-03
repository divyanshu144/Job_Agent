# JobFit Agent — Interview Deep-Dive

A senior-engineer walkthrough of *how* and *why* the system is built, grounded in the codebase.
Companion files: `interview-cheatsheet.md` (one-page), `interview-qa-drills.md` (rehearsal Q&A).

## 0. 30-second pitch
JobFit is an AI job-application assistant. Paste a JD → a **six-agent LLM pipeline** returns a fit
score, skill-gap analysis, learning plan, cover letter, and tailored résumé bullets — **streamed
live over SSE**. A **background pipeline** scrapes job boards (HN/Reed/Adzuna), scores them on a
cheaper model, and surfaces a ranked feed. Stack: FastAPI · async SQLAlchemy 2.0 · SQLite · React/
Vite/TS · Anthropic SDK.

**Lead line:** *"The hard part isn't the prompts — it's orchestrating a non-deterministic,
partially-failing, multi-model pipeline with cost control and observability."*

## 1. The four constraints that shaped everything
1. LLM calls are **slow, expensive, and fail partially** — not a normal function call.
2. It's a **pipeline** — later agents depend on earlier outputs.
3. **Two workloads:** interactive analysis (latency-sensitive, watched) vs. bulk discovery
   (throughput-sensitive, unwatched).
4. **Cost must be observable and controllable** or it runs away.

Every decision below traces to one of these.

## 2. System design

Two request shapes — the headline insight:

| Workload | Transport | Concurrency | Why |
|---|---|---|---|
| Manual analysis | **SSE** | sequential → `asyncio.gather` | user watching → live per-agent progress |
| Discovery | **POST returns `run_id`, client polls GET** | `create_task` + `Semaphore(5)` | minutes-long, unwatched → fire-and-forget |

Layering is strict: **route → service → agent → Anthropic SDK** (no skipping).
External integrations: Anthropic · HN/Reed/Adzuna (httpx) · Hunter.io · GitHub · Gmail.

## 3. Agent layer (`BaseAgent`)
One base class so cost logging, tiering, and parsing are uniform and free.
- **Prompts in versioned `.md` files** — the most-iterated artifact becomes a reviewable diff.
- **`_inject()`** fills `{profile}/{jd}/{prior.*}`; odd-shaped leaf agents use manual `.replace` —
  deliberate "don't over-abstract."
- **`with_tracking(db, run_id, analysis_id)`** attaches session + correlation IDs per request;
  agents are **fresh per request, never reused** (reuse leaks the prior request's session/run_id).
- **Model tiering:** default Sonnet; orchestrator sets `agent.model = HAIKU` for discovery (~20×
  cheaper). Model choice is a **runtime dispatch decision**, not a static property.
- **Typed parsing:** JSON → Pydantic schema → re-raise as `AgentError` so the orchestrator can do
  partial success instead of 500-ing.

## 4. Orchestration (two-phase pipeline)
- **Phase 1 sequential:** job_parser → match_scorer → gap_analyst, threaded via immutable
  `PriorOutputs.model_copy(update=...)`. Sequential because of data dependencies.
- **Phase 2 concurrent:** resource_planner, then cover_letter ∥ resume_tailorer via
  `asyncio.gather(return_exceptions=True)` — independent doc-writers parallelized for latency.

Three memorizable patterns:
1. **Partial success** — each agent in its own `try/except AgentError`; failure → `partial=True`,
   pipeline continues; successes persisted in `finally`. All-or-nothing is the wrong failure model
   for a 6-step pipeline.
2. **Per-coroutine sessions** — each parallel agent opens its own `SessionLocal`. *Real bug:* a
   shared `AsyncSession` across `gather` coroutines corrupts SQLAlchemy's unit-of-work.
3. **SSE protocol is a contract** — fixed order ending in `pipeline_done` (frontend aborts on it);
   names hardcoded client-side; emitting after `pipeline_done` is unreachable.

**Caching:** `jd_hash = sha256(jd + "::" + profile.id)` short-circuits the pipeline. *Known limit:*
keyed on `profile.id`, not content → stale on profile edits (name it unprompted in a review).

## 5. Discovery subsystem
- **Funnel:** `discovered → free keyword filter → Haiku relevance → Phase-1 scoring → scored`. Never
  pay LLM cost on a job a free string match rejects.
- **Multi-source fan-out** via `gather`, per-source status under an `asyncio.Lock`, bounded by
  `Semaphore(5)`.
- **Background tasks** held in a module set (`_background_tasks`) so Python's GC doesn't cancel them.
- **Batch API path** for 50% cheaper non-urgent scoring (trade latency for cost).

War stories: **zombie state** (Phase-1 failure left jobs stuck in `discovered` → transition to
`filtered`; every state needs a failure exit) and **swallowed exceptions**
(`gather(return_exceptions=True)` returns exceptions as values — must be inspected, not discarded).

## 6. Data layer
- Async SQLAlchemy 2.0, `expire_on_commit=False`.
- **Session ownership is a first-class design question:** request → `Depends(get_db)`; background
  task → owns `async with SessionLocal()`; concurrent coroutine → its own.
- **Migrations without a framework:** `create_all` + `PRAGMA table_info` + guarded `ALTER TABLE ADD
  COLUMN` at startup — additive/idempotent. Fine for SQLite; team Postgres → Alembic.
- **SQLite is single-writer** — right for a local single-candidate app, first scaling move is Postgres.

## 7. Observability & cost (the maturity signal)
- **`tracked_call`** writes one `LLMCall` row per call (tokens, real per-model `cost_usd`, latency,
  cache tokens, run_id/analysis_id), **fail-open**.
- **`PipelineEvent`** = per-agent spans + failures, keyed on a `trace_id` contextvar.
- **`/metrics/costs/*`** dashboard: per-run/agent cost, p50 latency, tiering savings.

**Best challenge story — prompt caching that lost money:** dashboard showed 21K cache *writes*, **0
reads**. Caching is a prefix match, but the system prompt interpolated profile/JD/prior into itself
→ unique prefix every call → never read. Plus Haiku's 4,096-token minimum >> our ~400-token prompt.
Modeled the break-even for padding → **negative at any call count** (a discounted 4,096-token read >
the un-padded 380-token full-price prompt). Conclusion: remove caching; only re-add for a large
*fixed* prefix. A decision backed by unit economics, including the willingness to delete code.

## 8. Frontend
- **SSE consumer** parses frames → typed callbacks → aborts on `pipeline_done`.
- **Polling** for discovery: 3s interval, terminal-state exit, **attempts cap → `timedOut`**.
- **Optimistic updates with revert** (save-job star).
- **Async UI as explicit state machines** (`idle→evaluating→evaluated→generating`;
  `idle→running→complete|failed|timedOut`) — kills impossible-combo bugs.
- **Schema-drift CI check** makes backend/frontend type divergence a build failure.

## 9. Cross-cutting conventions
Config singleton (no raw `os.environ`); all I/O async (`run_in_executor` for pypdf); `make check`
(fmt+lint+mypy+schema-drift+pytest ≥70%) as the single "done" gate; a session harness
(HANDOFF/todo/lessons, plan-before-build) treating the dev process itself as engineered.

## 10. Testing
TDD RED→GREEN; mock `Agent.run`/`_call` with `AsyncMock`; in-memory SQLite; auth-override vs.
unauthenticated clients (every route gets happy-path + 401); Definition of Done baked in.

## 11. Where it breaks at scale / what I'd change
1. SQLite → Postgres (single-writer serializes discovery; `pipeline_events` unbounded).
2. Discovery commits 7–9× per job → batch into one transaction.
3. No multi-tenancy on `Job`/`DiscoveryRun` (global feed).
4. `jd_hash` keyed on profile.id not content.
5. No retry observability (SDK retries opaque).
6. Background tasks die with the process → durable queue (Celery/Arq) for real durability.
7. Prompt caching removed — re-add only for a large fixed prefix.
