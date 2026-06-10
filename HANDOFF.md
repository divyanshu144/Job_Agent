# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — plan delivered; unrelated WIP uncommitted in tree

---

## Current State

Two unrelated threads in the working tree:

1. **Multi-tenant overnight campaign — PLAN ONLY, delivered (no code written).**
   Recommendation + prompt-by-prompt plan returned in chat for approval. Summary:
   build a parallel multi-tenant campaign path (Redis + Celery worker/beat,
   per-user `UserTargetCompany`, `CampaignRun`, `LLMCall.user_id` + per-user caps,
   nightly dispatcher) that REUSES `run_evaluate_pipeline`/`run_generate_pipeline`
   (driven from a Celery task) + the existing user-scoped `/history`,
   `/analysis/{id}`, and resume `.docx`. Admin `campaign_orchestrator`
   (Hunter/Gmail/LaTeX) stays untouched. Flagged risks: async-pipeline-in-Celery
   bridge; concurrent per-user cost-cap accuracy. Suggested first spike: a
   campaign-job evaluate/generate driver invoked outside a request (plan unit 4).
   Awaiting approval before any code.

2. **Work at a Startup source + `job_shortlist` service — COMMITTED** as
   `94c28fb` (owner-confirmed prior-session WIP; `make check` green, 411 passed,
   80.93%). Committed alone, no campaign work mixed in.

## Next Action

Approve / adjust the multi-tenant campaign plan, then implement plan unit 1
(Celery+Redis skeleton) or unit 4 (the de-risking spike). Separately, the WIP
author should finish + commit (or stash) the Work-at-a-Startup source.

## Why It Stopped

Plan delivered; awaiting approval. No code to commit for the planned feature.

## In-Flight

No uncommitted changes (WAAS WIP committed as `94c28fb`).

## Open Questions

- Cap model: `User` fields vs. a `UserCampaignSettings` table?
- Include on-demand "run my campaign now" in v1, or nightly-only?

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 411 passed, 1 deselected · 80.93% (with WAAS WIP) |
