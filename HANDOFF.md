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

Await direction. Shipped (all pre-queue): unit 4 (`9a3cff1`, headless driver),
unit 3 (`0366170`, cost attribution + caps), unit 2 (`030dd63`, per-user target
lists + `/api/targets` CRUD + parametrized `fetch_target_jobs`). Next: unit 1
(Celery+Redis skeleton + worker/beat services) and unit 5 (`run_user_campaign`
task — wires targets→discovery→per-job evaluate/generate, and is where
`daily_run_cap` enforcement lands via a `CampaignRun` record). Frontend (unit 8)
can follow.

## Why It Stopped

Unit 2 complete; awaiting next-unit direction. Still pre-queue (no Redis/Celery).

## In-Flight

No uncommitted changes.

## Open Questions

None (cap model + v1 scope decided). Note: `daily_run_cap` column exists but is
NOT yet enforced — deferred to unit 5 (needs a CampaignRun record to count runs).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 427 passed, 1 deselected · 81.24% |
