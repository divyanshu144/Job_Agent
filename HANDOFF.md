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

Await direction on the next unit. Spike done; queue work intentionally NOT
started. Logical next units: unit 2 (`UserTargetCompany` + `/api/targets` CRUD +
parametrize `fetch_target_jobs`), unit 3 (`LLMCall.user_id` + `UserCampaignSettings`
caps), then unit 1 (Celery+Redis skeleton) and unit 5 (`run_user_campaign` task).

## Why It Stopped

Plan unit 4 complete; reporting the spike finding before any Redis/Celery work,
as instructed.

## In-Flight

No uncommitted changes.

## Open Questions

None (cap model + v1 scope decided).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 412 passed, 1 deselected · 81.08% |
