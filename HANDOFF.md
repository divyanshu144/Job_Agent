# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — pipeline retry SHIPPED (backend + frontend); commit pending

---

## Current State

The **pipeline retry feature is fully shipped** — backend (Prompts 1–6) and
frontend (Prompts 7–8).

Backend (committed `3f2b7d7`): `to_user_error()` error boundary, `upsert_job_result()`
(one row per (analysis, agent)), migration `0003` (error_code/retry_count/
retry_running_at + dedup), `run_steps()` single runner, `run_retry_pipeline`
with the `retry_running_at` conditional-UPDATE concurrency claim, Phase-1 broad
catch + Phase-2 gather narrowed (re-raising KeyboardInterrupt/SystemExit), route
`POST /api/analysis/{id}/retry`, `AnalysisDetail.steps`.

Frontend (this pass, uncommitted): `Step`/`RetryRequest` TS types + `steps` on
`AnalysisDetail`; `retryAnalysis()` in `api/client.ts` (reuses `_streamSSE`);
`Results.tsx` per-step status strip (✓/✗/…/– across both phases with a divider),
per-step "retry" + "Retry all failed" buttons, `isRetrying` double-click guard,
DOCX download label. The resume-only red retry card was removed in favour of the
generic strip. SSE event names unchanged.

## Next Action

No work in progress. Candidate next features: (a) retry telemetry surfaced in the
admin cost dashboard (retry_count / error_code aggregates), or (b) auto-retry with
backoff for `rate_limited`/`upstream_timeout` codes. Neither is started.

## Why It Stopped

Task complete — retry feature shipped end to end; `make check` green and frontend
`npm run build` clean.

## In-Flight

Uncommitted (frontend pass):
- frontend/src/types/index.ts, frontend/src/api/client.ts, frontend/src/pages/Results.tsx
- tasks/lessons.md, HANDOFF.md

## Open Questions

None.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | ✓ 385 passed, 1 deselected · 80.33% coverage |
| `make lint` | ✓ clean (ruff + mypy + pydantic→TS drift) |
| `npm run build` (frontend) | ✓ tsc -b + vite build, no TS errors |
| `make check` | ✓ clean (run 2026-06-10) |
