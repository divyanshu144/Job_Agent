# Session Handoff

**Updated:** 2026-06-01  
**Branch:** chore/harness-hooks  

---

## Current State

Implementing the approved Observability & Instrumentation plan
(`~/.claude/plans/atomic-beaming-hamming.md`). TDD throughout.

**Wave 2 done (this checkpoint, on top of 0/1/5 committed in `0d0fccd`):**
- trace_id set at entry points: `run_evaluate_pipeline`, `run_generate_pipeline`, per-job in
  discovery `_process_job`, and run-level in `_run_discovery_task`/`_run_source_task`.
- Per-agent `span()` around every `agent.run()` in `_run_phase1`, `run_evaluate_pipeline`, and
  Phase-2 of `run_generate_pipeline` (parallel agents wrapped inside `_tracked`).
- Failure capture: agent failures now write `JobResult.error` (was unused) and an error span;
  discovery stage2/phase1 failures emit `kind="failure"` events with run_id.
- Tool-call logs: discovery source fetches wrapped in `span(kind="tool", name="fetch_<src>")`.
  **Deferred:** tool-logging for `contact_discovery` (Hunter) and `github_client` — they're on
  non-pipeline entry paths with no established trace; lower value, follow-up if wanted.
- Retry: explicit `max_retries=settings.anthropic_max_retries` (default 3) on both Anthropic
  clients (base.py, discovery.py). Final failures surface via the error spans/failure events.
- Tests: +4 (`test_pipeline_events.py` ×3, retry assert ×1). Full suite **177 passed**, lint clean.

**Previously done:**
- **Wave 5 (docs):** corrected `tasks/observability-audit.md` #8 to "evals scaffolded-but-lost"
  (the eval source `backend/evals/validators.py` + `test_evals/` existed locally per 2026-05-30
  bytecode but was never committed / is unrecoverable). Added Open Questions
  (`pipeline_events` growth, lost evals).
- **Wave 0 (logging foundation):** `trace_id_var` contextvar + `new_trace_id()`/`get_trace_id()`,
  `JsonLogFormatter`, `TraceIdFilter`, `configure_logging()` (idempotent) — all in
  `backend/services/instrumentation.py` (colocated with trace_id to avoid a config↔instrumentation
  import cycle; `config.py` only gained `log_level`). Wired `configure_logging()` into `main.py`
  lifespan.
- **Wave 1 (events):** `PipelineEvent` model (`models.py`, indexed on `(trace_id, kind)`,
  nullable `analysis_id`/`run_id` as plain strings — not FKs, to avoid cascade coupling).
  `log_event()` (fail-open) + `span()` async context manager in `instrumentation.py`.

**Verification:** `make fmt` clean, `make lint` clean (ruff + mypy + schema drift), full suite
**173 passed** (was 150; +9 new observability tests in `tests/test_services/test_observability.py`,
+ pre-existing growth).

## Next Action

**Wave 4 — feedback track** (Wave 3 "unify" is satisfied: trace_id flows to logs + every event,
and events carry analysis_id/run_id to join LLMCall — verify with a quick query if desired):
1. `Feedback` model (`models.py`): id, analysis_id FK, agent_name nullable, rating int, note
   nullable, trace_id nullable, created_at. Created by `create_all` (no migration needed for fresh
   DB; add an `init_db` ALTER only if a pre-existing DB must gain it — table is new so create_all
   covers it).
2. `FeedbackCreate` / `FeedbackResponse` in `schemas.py` (+ TS mirror in `frontend/src/types`).
3. `backend/routes/feedback.py`: `POST {api_prefix}/feedback` (auth) + `GET ?analysis_id=`;
   register in `main.py`.
4. Frontend: thumbs/rating on `Results.tsx`; `submitFeedback` in `api/client.ts`.
5. `backend/evals/__init__.py` stub documenting the hook (reconstructable validators consume Feedback).
6. Tests: `tests/test_routes/test_feedback.py` happy + auth (401 unauth).

## Why It Stopped

Checkpoint after Wave 2 green. Committing to keep the tree clean.

## In-Flight

Committing now: orchestrator.py, discovery.py, base.py, config.py, models.py (no new model this
wave), instrumentation.py (no change this wave), test_pipeline_events.py, test_observability.py,
this HANDOFF. After commit the tree is clean.

## Open Questions

1. `pipeline_events` unbounded growth on SQLite (single-user → fine for now).
2. Whether/when to reconstruct the lost `backend/evals/validators.py` + `test_evals/` suite
   (separate track; feedback only wires the hook).

## Verification Baseline

| Check | Result |
|---|---|
| `make fmt` | ✓ 78 files unchanged |
| `make lint` | ✓ ruff + mypy + schema drift (9 classes) pass |
| `make test` | ✓ 177 passed (full `pytest`, run with `--no-cov`) |
