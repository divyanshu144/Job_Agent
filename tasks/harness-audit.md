# JobFit Agent — Harness Audit

**Date:** 2026-05-26  
**Status:** Read-only; no changes made  
**Purpose:** Case study for agent harness engineering discussion

---

## 1. Project Reality Check

### What JobFit Actually Does

JobFit is a two-phase AI-driven job-fit analysis and document generation platform. Users paste a job description; the system runs a six-agent pipeline: **job_parser** extracts structured JD requirements, **match_scorer** produces a 0–100 fit score against the candidate's profile, and **gap_analyst** identifies missing skills — these three run in Phase 1. If the user triggers generation, Phase 2 runs **resource_planner**, **cover_letter**, and **resume_tailorer** concurrently. Results stream to the browser over SSE in real time. A separate background pipeline discovers job postings from HackerNews, scores them with the same agents, and stores them in a discovery feed. A cold email workflow (recently added) discovers company contacts via Hunter.io and drafts outreach via an additional agent; Gmail sending is stubbed. Everything requires a candidate profile built from a YAML file, uploaded CV, and GitHub README scraping.

### Who It's For

Individual job seekers (inferred from single-user profile management, CV upload UX, and invite-token registration). Admin users get access to the cost monitoring dashboard (is_admin check in routes/metrics.py).

### Current State

**Mostly working.** The core analysis pipeline, discovery feed, auth, history, cost tracking, and cold email drafting are all implemented and tested. The Gmail send endpoint is a permanent 503 stub. There is one pending feature list (8 items in `tasks/todo.md`) that has not been started.

### Lines of Code

| Layer | Count |
|---|---|
| Backend Python (`backend/` + `scripts/`) | ~2,900 lines |
| Tests (`tests/`) | ~1,200 lines |
| Frontend TypeScript/TSX (`frontend/src/`) | ~2,400 lines |
| Prompts (`backend/prompts/*.md`) | ~136 lines (7 files) |

---

## 2. Instruction Subsystem

### Every File an Agent Might Read for Instructions

| File | Lines | Role |
|---|---|---|
| `CLAUDE.md` (project root) | 142 | Primary instruction file: stack, commands, architecture map, conventions, workflow, principles |
| `RESOLVER.md` (project root) | 43 | Maps task types to skills (brainstorming, plans, review, debug, pr-checklist) |
| `.claude/skills/conventions.md` | ~105 | Cross-cutting constraints: config import, DB sessions, async rules, API prefix |
| `tasks/todo.md` | 26 | Task checklist (state of active work) |
| `tasks/lessons.md` | 10 | Template only — no entries logged |
| `backend/prompts/*.md` | 15–28 each | LLM prompt templates (not human instructions, but read by agents via `_load_prompt()`) |
| `docs/superpowers/plans/2026-05-*.md` | varies | Per-feature implementation plans (8 files) |
| `docs/superpowers/specs/2026-05-*.md` | varies | Design specs (2 files) |

**Total instruction overhead read on a typical session start:** ~400–500 lines across CLAUDE.md + RESOLVER.md + conventions.md.

### CLAUDE.md Drift Check

The architecture map at `CLAUDE.md:32–76` matches the actual file tree closely. Two gaps:

1. **Stale TODO** — `CLAUDE.md:5–6` says *"TODO: Fill in once application scaffolding is complete"*; the app is complete.
2. **Missing routes** — `CLAUDE.md` lists `profile.py`, `analyse.py`, `history.py` but the actual `routes/` directory has seven files: add `auth.py`, `discovery.py`, `contacts.py`, `metrics.py`. Same for frontend pages: `Costs.tsx`, `Discover.tsx`, `Saved.tsx`, `Login.tsx`, `Register.tsx` are not in the map.

### Conventions in Code Not Documented in CLAUDE.md

1. **SSE event protocol** — `orchestrator.py:149–196` emits a specific ordered sequence: `pipeline_start → agent_start → agent_done → pipeline_error → pipeline_done`. The schema (field names, data shapes) is not documented anywhere. Frontend `client.ts:136–147` hard-codes the same event names.

2. **`_inject()` vs manual `.replace()` convention** — Phase 1–2 agents use `self._inject(template, profile, jd, prior)` defined in `base.py`. `ColdEmailAgent` (`cold_email_agent.py:18–23`) uses manual `template.replace("{profile}", ...)` instead. No rule explains when each is appropriate.

3. **`with_tracking()` chaining pattern** — Agents call `ColdEmailAgent().with_tracking(db, analysis_id=analysis.id)` (contacts.py:73) to attach DB session for cost logging. The orchestrator does this differently — it passes `db` and `run_id` as constructor args (orchestrator.py:110–119). Two patterns, no documented rule.

4. **Model tiering at runtime** — `orchestrator.py:122` mutates `agent.model` at dispatch time (`agent.model = model`). This is not in the agent's `__init__` and not documented in CLAUDE.md conventions.

5. **JD hash caching** — `orchestrator.py:62–92` computes `jd_hash` + `profile_id` and returns a cached `Analysis` if it exists. Profile updates do not invalidate this cache. Not documented.

---

## 3. Tool Subsystem

### Tools Available to an Agent on This Repo

| Tool | Configured | Where |
|---|---|---|
| Bash / shell | Yes | Standard Claude Code |
| File read/write/edit | Yes | Standard Claude Code |
| code-review-graph MCP (`semantic_search_nodes`, `get_impact_radius`, etc.) | Yes | `.code-review-graph/graph.db` exists (2 MB), last updated 2026-05-26 01:46 |
| Supermemory MCP | Mentioned in CLAUDE.md line 140 ("Check Supermemory at session start") | Not verified as actually connected |
| Gmail MCP (`mcp__claude_ai_Gmail__*`) | Present in session deferred tools | Not wired to application code; send endpoint is a 503 stub |
| Figma MCP | Present in session | Not relevant to this codebase |
| `.claude/skills/` (conventions, fde-plan, fde-review, debug-playbook, pr-checklist, api-conventions) | Yes | `RESOLVER.md` routes to them |

### Tools Mentioned in CLAUDE.md That Are Uncertain

- **Supermemory** (`CLAUDE.md:140`): "Check Supermemory at session start for persisted context." No `.supermemory/` config or MCP config in the project directory. Whether it's actually connected depends on the session environment — not verifiable from the repo alone.

### Tools That Exist But Aren't Mentioned

- **Gmail MCP** — available in the Claude Code session (visible in deferred tools list) but not mentioned in CLAUDE.md and not wired to any application code.

---

## 4. Environment Subsystem

### Reproducibility

| Artifact | Present | Notes |
|---|---|---|
| `Dockerfile` | Yes (19 lines) | Multi-stage: `node:20-alpine` builds frontend, `python:3.11-slim` runs backend |
| `docker-compose.yml` | Yes (10 lines) | Single service, mounts `./data`, reads `.env` |
| `.python-version` | **No** | Python version only pinned inside Dockerfile |
| `.nvmrc` | **No** | Node version only pinned inside Dockerfile |
| `backend/requirements.txt` | Yes | **All floating** (`fastapi>=0.115.0`, `anthropic>=0.40.0`, etc.) — no lock file |
| `frontend/package-lock.json` | Yes | npm lockfile present; Node deps reproducible |
| `.env.example` | Yes (8 vars) | `ANTHROPIC_API_KEY`, `GITHUB_USERNAME`, `DATABASE_URL`, `HUNTER_API_KEY`, and 4 others |

### What Fails on `git clone && make run`

1. **Missing `.env`** — `make run` starts uvicorn which loads `backend/config.py`; `pydantic-settings` will raise `ValidationError` if `ANTHROPIC_API_KEY` is missing. Fix: copy `.env.example` → `.env` and populate.
2. **Wrong Python version** — no `.python-version`; if the system has Python 3.10 or 3.12, `match` statements and some type hints may fail. `Makefile` has no `python3.11` enforcement.
3. **pip floating deps** — `pip install -r requirements.txt` installs latest-compatible; a new Anthropic SDK major version (e.g., 0.50+) could break the `AsyncAnthropic` import path.
4. **No DB migrations** — the database is auto-created by `init_db()` in `main.py` lifespan. For a fresh clone this works. For an existing DB after a schema change (new column), it silently breaks — there's no Alembic migration system.
5. **GitHub rate limits** — unauthenticated GitHub API calls are capped at 60/hour. If `GITHUB_USERNAME` has many repos, `github_client.py` will hit 403 silently (returns empty list, no hard failure).

---

## 5. State Subsystem

### State Files

| File | Exists | Content |
|---|---|---|
| `tasks/todo.md` | Yes | 26 lines; 8 completed Pipeline Optimisation tasks, 8 pending Feature Improvement tasks |
| `tasks/lessons.md` | Yes | 10 lines; header template only — zero entries logged |
| `docs/superpowers/plans/` | Yes | 8 plan files (2026-05-21 through 2026-05-25) |
| `docs/superpowers/specs/` | Yes | 2 spec files |
| `PROGRESS.md` | **No** | Does not exist |
| `.claude/memory/` | Yes (parent project) | Lives at `~/.claude/projects/…/memory/`; separate from this repo |

### How a New Session Knows Where the Previous Left Off

It doesn't, automatically. A new session must:
1. Read `CLAUDE.md` for project context
2. Read `tasks/todo.md` to see which tasks are complete
3. Read any relevant plan file in `docs/superpowers/plans/`
4. Use `git log` or `git status` to see recent changes

There is no single "resume here" document. `tasks/lessons.md` was intended for cross-session learning but has never been used.

---

## 6. Feedback / Verification Subsystem

### All Available Make Targets

```
make run        — uvicorn :8000 (backend, --reload) + npm run dev :5173 (frontend), concurrently
make test       — pytest tests/ -v --cov=backend --cov-report=term-missing --cov-fail-under=70
make fmt        — ruff format backend/ tests/ (auto-fix)
make lint       — ruff check backend/ tests/ + mypy backend/ + python scripts/check_schema_drift.py
make docker-up  — docker-compose up --build
```

**No single all-verification command.** Users must chain: `make fmt && make lint && make test`. There is no `make check`.

### Agent Output Validation

All 7 agents follow the same pattern (`job_parser.py:29–37` is representative):

```python
raw = await self._call(system, jd)
try:
    data = _parse_json(raw)         # strips markdown fences, parses JSON
    return SomeOutput.model_validate(data)   # Pydantic v2 strict validation
except (json.JSONDecodeError, ValidationError, AgentError) as e:
    raise AgentError(f"agent_name: {e}") from e
```

No agent returns unvalidated output. On failure, `AgentError` propagates to the orchestrator which sets `partial=True` and continues.

### Tests for Agents

Every agent has a dedicated test file under `tests/test_agents/`:

| Test File | What It Tests |
|---|---|
| `test_job_parser.py` | Mocks `_call()` return, validates `JobParserOutput` fields |
| `test_match_scorer.py` | Mocks `_call()`, validates score range and lists |
| `test_gap_analyst.py` | Mocks `_call()`, validates gap structure |
| `test_resource_planner.py` | Mocks `_call()`, validates resource list |
| `test_cover_letter.py` | Mocks `_call()`, validates subject/body |
| `test_resume_tailorer.py` | Mocks `_call()`, validates bullet rewrites |
| `test_cold_email_agent.py` | Mocks `_call()`, validates ColdEmailOutput |
| `test_model_tiering.py` | Validates Haiku is used for job_parser/match_scorer |

**All tests mock Anthropic responses** — no live LLM calls in tests. Tests verify that Pydantic schemas accept the mock output and that `AgentError` is raised on malformed responses. They do **not** test that real prompts produce real output in the right format.

### Current Test Coverage

- **131 tests passing, 0 failing**
- **79.22% coverage** (threshold: 70%)
- Coverage enforced via `pytest.ini`; CI would fail if coverage drops below 70%

---

## 7. Agent / LLM Specific Audit

### All Agents

| Agent | Model | max_tokens | Prompt Lines | Input Slots |
|---|---|---|---|---|
| `JobParserAgent` | `claude-haiku-4-5-20251001` | 4096 | 15 | `{profile}`, `{jd}` |
| `MatchScorerAgent` | `claude-haiku-4-5-20251001` | 4096 | 18 | `{profile}`, `{jd}`, `{prior.job_parser}` |
| `GapAnalystAgent` | `claude-sonnet-4-6` | 4096 | 18 | `{profile}`, `{prior.match_scorer}`, `{prior.job_parser}` |
| `ResourcePlannerAgent` | `claude-sonnet-4-6` | 4096 | 15 | `{profile}`, `{jd}`, `{prior.gap_analyst}` |
| `CoverLetterAgent` | `claude-sonnet-4-6` | 4096 | 28 | `{profile}`, `{jd}`, `{contact_name}`, `{contact_title}` |
| `ResumeTailorerAgent` | `claude-sonnet-4-6` | 4096 | 21 | `{profile}`, `{jd}`, `{prior}` |
| `ColdEmailAgent` | `claude-sonnet-4-6` | 4096 | 28 | `{profile}`, `{jd}`, `{contact_name}`, `{contact_title}` |

Model is set as a class attribute (`model: str = SONNET`) in each agent file and can be overridden at dispatch time via `agent.model = model` in the orchestrator (`orchestrator.py:122`). The discovery pipeline uses this to force Haiku for bulk scoring.

### Retry Logic

**None.** There is no retry, backoff, or circuit breaker anywhere in the agent call path. If `client.messages.create()` raises (network error, API timeout, 529 overload), the exception propagates immediately. The orchestrator catches `AgentError` but not raw Anthropic SDK exceptions — those would propagate to the route and become unhandled 500s.

### Output Validation

**Yes, enforced.** All agents use Pydantic `model_validate()` on the parsed JSON. Malformed output raises `AgentError`. The orchestrator catches this and marks the analysis partial, not crashed.

### Cost Tracking

**Comprehensive.** `backend/services/instrumentation.py` wraps every `client.messages.create()` call via `tracked_call()`. It logs to the `llm_calls` table: agent name, model, input tokens, output tokens, cost (computed from known Haiku/Sonnet per-million rates), latency (ms), cache_hit flag, run_id, analysis_id. A `/api/metrics/costs/` endpoint exposes summary and per-run breakdowns.

### Caching

**JD-level result caching** (not prompt caching):
- `orchestrator.py:62–92` hashes `jd_text + profile_id` and returns a cached `Analysis` if it exists. This prevents re-running Phase 1 for an identical JD + profile.
- **No Anthropic prompt caching** (no `cache_control` headers). Every API call regenerates the full system prompt. At Sonnet prices, a typical Phase 2 run (~6000 input tokens) costs ~$0.018 per run. Prompt caching headers could reduce this by ~40% on repeated prompts.

---

## 8. Honest Failure Modes

### Git History

```
a346953 job-agent-complete
```

Single commit — this is a newly initialized repo. No history of bugs, regressions, or fixes to analyze.

### TODOs and FIXMEs in Code

Zero `TODO`, `FIXME`, `HACK`, or `XXX` comments in `backend/` or `frontend/src/`. One documentation stub:

- `CLAUDE.md:5–6`: `"TODO: Fill in once application scaffolding is complete"` — stale, the app is complete.

### Known Stubs

| File | Line | What It Does | Impact |
|---|---|---|---|
| `backend/routes/contacts.py` | 128–131 | Gmail send raises 503 unconditionally | Cold email feature unusable end-to-end |

### tasks/lessons.md

Empty. The CLAUDE.md workflow calls for logging patterns after every correction (`tasks/lessons.md`), but no entries have ever been written. This means the cross-session learning loop documented in CLAUDE.md is not operational.

### Structural Failure Modes (From Code Reading)

**1. No DB migration system**  
`init_db()` calls `Base.metadata.create_all()` which only creates missing tables — it does not add missing columns to existing tables. Adding a column to `models.py` without a corresponding migration leaves existing databases silently broken. There is no Alembic setup. The project has `scripts/migrate.py` with manual `ALTER TABLE` SQL, but it's not idempotent and requires manual invocation.

**2. No retry on LLM calls**  
A transient 529 (API overloaded) or network error during a 15-second Phase 2 run causes the entire generation to fail with a 500. The user sees a broken SSE stream with no recovery path.

**3. JD hash cache does not invalidate on profile update**  
If a user updates their profile (uploads a new CV, refreshes GitHub) and re-runs the same JD, `orchestrator.py:62–92` returns the cached `Analysis` from before the profile update. The score and gaps reflect the old profile, not the new one. `jd_hash` is computed only from `jd_text + profile_id`, not from profile content.

**4. CV extraction silent failure**  
`profile_builder.py` wraps PDF text extraction in a try/except that returns an empty string on failure. A corrupted CV silently produces an empty `cv_text`; the profile is built without CV data, and the user receives no warning.

**5. GitHub unauthenticated rate limit**  
`github_client.py` makes unauthenticated requests to `api.github.com`. The limit is 60 requests/hour. A user with 30+ repos would exhaust this in one profile refresh. The client returns an empty list on 403, which silently drops GitHub data from the profile.

**6. Floating Python dependencies**  
`requirements.txt` uses `>=` for all packages. A breaking change in a new minor version of `anthropic`, `fastapi`, or `sqlalchemy` would only be caught at install time, not at test time. There is no pip-tools or Poetry lock file for the backend.

**7. No all-in-one verification command**  
`make check` doesn't exist. A contributor who runs only `make test` skips ruff and mypy. The schema drift check (`scripts/check_schema_drift.py`) is only in `make lint`, not in `make test`.

---

*Audit complete. All findings are read-only observations. No files were modified.*
