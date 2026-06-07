# Session Handoff

**Updated:** 2026-06-07
**Branch:** main (synced with `origin/main`); live-ATS fix on `fix/ats-live-shapes`

---

## Current State

**Live ATS shape check COMPLETE** (step 2 of: branch cleanup → live ATS check → Prompt 2).
`make check` green (**254 passed, 77.31% cov**). Hit one real endpoint per source and reconciled
normalizers/fixtures to the true shapes.

**Findings & fixes:**
- **Greenhouse** — legacy `boards.greenhouse.io/{slug}/jobs.json` 404s. Fixed endpoint to
  `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`. Its `content` is HTML-**escaped**,
  so `_normalise_greenhouse` now `unescape→strip`s (was leaving visible tags). Test fixture updated
  to escaped content + asserts no tags/entities survive.
- **Remotive / Lever / Ashby** — endpoints + shapes verified correct against live data; no code
  change (my dead test slugs were the only issue).
- **YC** — `v0.1/companies` has **no `jobs_url`/ATS field** (only `website` + YC profile `url`); the
  YC→ATS passthrough was infeasible. **Per decision: dropped the YC source** — removed `yc_client.py`,
  its 3 tests, the dispatch branches (3 sites), `_get_configured_sources` entry, `_VALID_SOURCES`,
  and the `/discovery/sources` key. Curated YC companies go in `target_companies.json` with explicit
  `ats`+`slug`.
- **HN kept** — untouched; remains the default source.

**Active source set:** `hn`, `remotive`, `reed`/`adzuna` (keyed), `targets` (when list populated).

## Next Action

**Prompt 2 — CampaignJob model + orchestrator skeleton.** The normalizers are now validated against
real payloads, so the Job-schema normalization the orchestrator builds on is trustworthy.

## Why It Stopped

Live-check fixes done + verified; ready for Prompt 2.

## In-Flight

On branch `fix/ats-live-shapes` (off `main`): `backend/services/ats_client.py`,
`backend/services/discovery.py`, `backend/routes/discovery.py`, deleted
`backend/services/yc_client.py`, `tests/test_services/test_new_sources.py`, `tasks/lessons.md`,
this HANDOFF. To merge into `main` + push.

## Open Questions

1. `feat/job-board-scrapers` + `feat/referral-clean` remain (local+remote) — unmerged, not named in
   cleanup. Delete too?
2. `Discover.tsx` source toggles still deferred (do when orchestrator is wired end-to-end).
3. Greenhouse/Lever/Ashby slugs in `target_companies.json` are placeholders — swap for real
   target-company slugs when known.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 254 passed, 1 deselected, 77.31% coverage |
| live endpoints | ✓ remotive/greenhouse(modern)/lever/ashby 200 + shapes reconciled; YC dropped |
