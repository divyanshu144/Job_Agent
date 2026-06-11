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

The multi-tenant campaign **backend is complete**. Shipped: unit 4 (`9a3cff1`),
unit 3 (`0366170`), unit 2 (`030dd63`), unit 1 (`b10228f`), unit 5 (`5d17a20`),
unit 6 (`c038b89`, nightly dispatcher via beat crontab @ 02:00 UTC →
`dispatch_campaigns` → one run per eligible user). Only **unit 8 (frontend)**
remains: targets management page (`/api/targets` CRUD), campaign dashboard
(`/api/campaign/run-now` + `/api/campaign/runs` + existing `/history` /
`/analysis/{id}` / resume `.docx`), and a usage/cap indicator.

## Why It Stopped

Unit 6 complete — backend done end to end (on-demand + nightly). Frontend is the
last unit.

## In-Flight

No uncommitted changes.

## Open Questions

None (cap model + v1 scope decided). Note: `daily_run_cap` column exists but is
NOT yet enforced — deferred to unit 5 (needs a CampaignRun record to count runs).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 446 passed, 1 deselected · 81.61% |
