# Session Handoff

**Updated:** 2026-06-01  
**Branch:** chore/harness-hooks  

---

## Current State

Implementing the approved Observability & Instrumentation plan
(`~/.claude/plans/atomic-beaming-hamming.md`). TDD throughout.

**Done this checkpoint:**
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

**Wave 2 — stamp signals onto the spine.** In order:
1. `new_trace_id()` at entry points: `run_evaluate_pipeline`, `run_generate_pipeline`
   (orchestrator.py), `run_discovery` / `_run_all_discovery_task` (discovery.py).
2. Per-agent `span(kind="span", name=agent_name)` around each `agent.run()` in `_run_phase1`,
   `run_evaluate_pipeline`, and Phase-2 of `run_generate_pipeline`.
3. Failure capture: in `except AgentError` arms also `log_event(kind="failure", ...)` AND set
   `JobResult.error = str(e)`; convert discovery `logger.warning` arms to also emit failure events.
4. Tool-call logs: one shared httpx helper wrapping client calls (hn/reed/adzuna/contact/github).
5. Retry: explicit `max_retries` on `AsyncAnthropic(...)` in base.py:25 + discovery.py:31; log
   final failure.

Then Wave 3 (verify unify) and Wave 4 (feedback model/route/frontend + `backend/evals/__init__.py`
hook stub).

## Why It Stopped

Checkpoint after Waves 5/0/1 green. Committing to keep the tree clean.

## In-Flight

Committing now: `tasks/observability-audit.md`, `tasks/todo.md`, `backend/config.py`,
`backend/main.py`, `backend/models.py`, `backend/services/instrumentation.py`,
`tests/test_services/test_observability.py`, this HANDOFF. After commit the tree is clean.

## Open Questions

1. `pipeline_events` unbounded growth on SQLite (single-user → fine for now).
2. Whether/when to reconstruct the lost `backend/evals/validators.py` + `test_evals/` suite
   (separate track; feedback only wires the hook).

## Verification Baseline

| Check | Result |
|---|---|
| `make fmt` | ✓ 78 files unchanged |
| `make lint` | ✓ ruff + mypy + schema drift (9 classes) pass |
| `make test` | ✓ 173 passed (full `pytest`, run with `--no-cov`) |
