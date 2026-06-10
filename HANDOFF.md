# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — pipeline-retry backend complete (commit pending)

---

## Current State

The pipeline **retry backend** (Prompts 1–6) is implemented and verified.
New: `services/pipeline_errors.py` (to_user_error boundary), `services/job_result.py`
(upsert — one row per (analysis, agent)), Alembic `0003_pipeline_retry`
(JobResult.error_code/retry_count, Analysis.retry_running_at, one-time dedup).
`orchestrator.py` now has `run_steps()` as the single runner for both phases;
`run_generate_pipeline` is a thin wrapper; `run_retry_pipeline` adds the
DB-claim concurrency guard and resolves failed/missing steps (never re-runs a
succeeded step unless scope=all+admin). Phase-1 catches broad Exception and
maps via to_user_error; Phase-2 gather narrows BaseException→Exception while
re-raising KeyboardInterrupt/SystemExit. Route `POST /api/analysis/{id}/retry`
(SSE, ownership-scoped). `AnalysisDetail.steps` derived in the history route;
`result_errors` now user-safe. SSE event names unchanged → client.ts untouched.

## Next Action

Frontend wiring (Prompt 7, not in this pass): a per-step status strip + retry
buttons in `Results.tsx`, `retryAnalysis`/`streamRetry` in `api/client.ts`, and
`Step`/`RetryRequest` TS types. Backend is ready and tested.

## Why It Stopped

Task complete — Prompts 1–6 implemented, `make check` green.

## In-Flight

To be committed in this checkpoint:
- backend/services/pipeline_errors.py, backend/services/job_result.py (new)
- alembic/versions/0003_pipeline_retry_fields.py (new)
- backend/models.py, backend/schemas.py, backend/services/orchestrator.py,
  backend/routes/analyse.py, backend/routes/history.py
- tests/test_services/test_pipeline_errors.py, tests/test_services/test_job_result.py,
  tests/test_orchestrator/test_retry.py, tests/test_routes/test_retry.py (new)
- tests/test_orchestrator/test_pipeline_events.py, tests/test_startup.py (updated assertions)
- tasks/agent_memory.md, tasks/todo.md, HANDOFF.md

## Open Questions

None.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | ✓ 385 passed, 1 deselected · 80.33% coverage |
| `make lint` | ✓ clean (ruff + mypy + pydantic→TS drift) |
| `make check` | ✓ clean (run 2026-06-10) |
