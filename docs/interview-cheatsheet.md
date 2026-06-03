# JobFit — One-Page Cheat-Sheet

**Pitch:** AI job assistant. Paste a JD → 6-agent LLM pipeline → fit score, gap analysis, learning
plan, cover letter, résumé bullets, **streamed over SSE**. Background pipeline scrapes job boards,
scores on a cheaper model, ranks a feed. FastAPI · async SQLAlchemy/SQLite · React/TS · Anthropic SDK.

**Opening line:** *"The hard part is orchestrating a non-deterministic, partially-failing,
multi-model pipeline with cost control and observability — not the prompts."*

## The 4 constraints (everything traces here)
slow/expensive/partially-failing LLM calls · it's a pipeline (data deps) · two workloads
(interactive vs bulk) · cost must be observable.

## Key decisions (say the *why*)
| Decision | Why |
|---|---|
| Two-phase: Phase 1 sequential, Phase 2 `asyncio.gather` | data deps then independent doc-writers |
| SSE for analysis, poll for discovery | watched/live vs detached/long |
| Sonnet default, **Haiku for discovery** (runtime dispatch) | ~20× cheaper on bulk |
| Free keyword filter → Haiku → Phase-1 scoring (funnel) | never pay LLM on a string-match reject |
| Partial success (per-agent try/except → `partial=True`) | all-or-nothing wrong for 6 steps |
| Per-coroutine `AsyncSession` in fan-out | shared session corrupts SQLAlchemy UoW |
| `tracked_call` → one `LLMCall` row/call, fail-open | DB-backed cost ledger → dashboard |
| Typed `AgentError` on bad JSON | orchestrator degrades, doesn't 500 |
| Schema-drift CI check | backend/frontend type drift = build failure |

## 3 war stories (one line each)
- **Prompt caching lost money:** 21K writes / 0 reads — unique prefix every call + below Haiku's
  4096 min; break-even negative at any N → removed it (decision via unit economics).
- **Shared async session across `gather`** corrupted the DB → one session per coroutine.
- **`gather(return_exceptions=True)` swallowed failures** (returned as values, discarded) → inspect them.
  (Also: GC cancelled detached `create_task`s → hold a strong ref.)

## System design diagram (draw this)
SPA ──fetch/SSE──▶ FastAPI (route→service→agent→Claude)
  • POST /analyse → orchestrator (2-phase) → SSE stream
  • POST /discovery/run/all → create_task (bg) → GET /runs/{id} poll
  • agents: Sonnet (analysis) / Haiku (discovery) → LLMCall + PipelineEvent ledger → /metrics

## Scaling answers (have these ready)
SQLite→Postgres (single-writer bottleneck) · durable job queue for discovery (tasks die with
process) · batch the 7–9 commits/job · add `user_id` for multi-tenancy · `jd_hash` should key on
profile *content* · partition funnel so free stage-1 runs before anything paid.

## Crisp Q&A bullets
- *Why pipeline not one prompt?* → separation, partial success, per-stage tiering, observability.
- *SSE vs WS vs poll?* → SSE = one-way server→client streaming (simplest fit); poll = detached long jobs.
- *Cost control?* → tiering + free pre-filter + Batch API + per-call cost ledger.
- *Bad JSON?* → typed `AgentError` → partial result, persist the rest.
- *Type sync?* → schema-drift check fails the build.
