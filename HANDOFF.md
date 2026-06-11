# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — plan delivered; unrelated WIP uncommitted in tree

---

## Current State

**Multi-tenant overnight campaign — APPROVED; plan unit 4 SHIPPED.** Locked
decisions: separate `UserCampaignSettings` table (not `User` fields); v1 scope
is on-demand "run now" first, nightly schedule second.

Plan unit 4 (headless pipeline spike) committed `9a3cff1`: `run_campaign_for_user(
user_id, db)` (`backend/services/campaign_user.py`) drives `run_evaluate_pipeline`
→ `run_generate_pipeline` in a plain async function — no FastAPI request, no SSE.
**Finding: the orchestrator generators are NOT request/SSE-coupled** (SSE
formatting lives only in `routes/analyse.py`); they persist user-scoped
Analysis/JobResult, already surfaced by `/history` + `/analysis/{id}` + resume
`.docx`. `make check` green (412 passed, 81.08%). The load-bearing assumption for
the whole feature is proven.

(Prior-session WIP "Work at a Startup source + job_shortlist" was committed
earlier as `94c28fb`, unrelated.)

## Next Action

Await direction. Shipped: unit 4 (`9a3cff1`, headless driver), unit 3 (`0366170`,
cost attribution + caps), unit 2 (`030dd63`, per-user targets), unit 1 (`b10228f`,
Redis+Celery infra). Next: **unit 5** — `run_user_campaign` Celery task wiring
targets → discovery (`fetch_target_jobs(user's rows)`) → per-job evaluate/generate
(via `run_campaign_for_user`, wrapped in `run_async` + `task_session`), a
`CampaignRun` record (where `daily_run_cap` enforcement lands), and on-demand
"run now" route. Then unit 6 (beat → nightly dispatcher) and unit 8 (frontend).

The async-in-Celery pattern is settled (see backend/tasks.py): `run_async` +
`task_session()` (fresh engine per task). Unit 5 builds directly on it.

## Why It Stopped

Unit 1 complete; awaiting next-unit direction.

## In-Flight

No uncommitted changes.

## Open Questions

None (cap model + v1 scope decided). Note: `daily_run_cap` column exists but is
NOT yet enforced — deferred to unit 5 (needs a CampaignRun record to count runs).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 432 passed, 1 deselected · 81.44% |
