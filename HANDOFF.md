# Session Handoff

**Updated:** 2026-06-07
**Branch:** feat/discovery-new-sources (off `chore/remove-github-profile-source`)

---

## Current State

**Three new discovery sources COMPLETE** (plan: `~/.claude/plans/atomic-beaming-hamming.md`,
approved). TDD throughout (17 tests written failing first, then implemented). `make check` green
(**251 passed, 77.45% cov** — prior 234 preserved + 17 new).

Added **Remotive** (keyless), **YC → ATS passthrough**, and a **manual target list**, all normalising
to the existing `RawJob` dataclass and returning `list[RawJob]` like `fetch_reed_jobs`.

**New modules (`backend/services/`):**
- `remotive_client.py` — `fetch_remotive_jobs()`; GET remotive software-dev API, HTML-stripped.
- `ats_client.py` — `detect_ats(jobs_url)`, `_extract_slug`, `fetch_ats_jobs(ats, slug)` dispatching
  Greenhouse/Lever/Ashby with per-provider normalisers. Shared by YC + targets.
- `yc_client.py` — `fetch_yc_jobs()`; YC hiring companies → detect ATS → aggregate. Per-company
  try/except continue; unknown-ATS companies skipped.
- `targets_client.py` — `fetch_target_jobs()`; reads `assets/target_companies.json`, queries ATS per
  entry. Missing/invalid file → []; malformed entries + per-entry errors skipped.

**Wiring (`discovery.py`):** new imports; additive `elif source == "remotive"/"yc"/"targets"`
branches before the `else` (HN) in all three fetch-dispatch sites (`_run_discovery_task`,
`_run_source_task`, `_run_batch_discovery_task`) — existing reed/adzuna/hn lines untouched.
`_get_configured_sources()` now always includes remotive+yc, adds targets when
`assets/target_companies.json` is populated (new `_target_list_present()` helper).

**Routes (`routes/discovery.py`):** `_VALID_SOURCES` extended with the three; `/discovery/sources`
response dict reports them.

**Asset:** `assets/target_companies.json` with 5 placeholder entries (greenhouse/lever/ashby mix).

**Note on ATS response shapes:** the Greenhouse/Lever/Ashby/Remotive/YC JSON field mappings are coded
defensively (`.get(...) or ""`) and pinned by mocked tests; if a live response differs, adjust the
per-provider normalisers in `ats_client.py` / `remotive_client.py`. No live calls were made.

## Next Action

Commit on `feat/discovery-new-sources`. Folds into the pending batch merge onto `main` alongside the
other stacked branches.

## Why It Stopped

Feature complete and verified. Committing.

## In-Flight

Committing now: new files `backend/services/{remotive,ats,yc,targets}_client.py`,
`assets/target_companies.json`, `tests/test_services/test_new_sources.py`; edits to
`backend/services/discovery.py`, `backend/routes/discovery.py`, this HANDOFF.

## Open Questions

1. Frontend Discover.tsx source toggles don't yet surface the 3 new sources (out of scope this pass).
2. Live response-shape validation against real Greenhouse/Lever/Ashby/YC payloads still pending.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 251 passed, 1 deselected, 77.45% coverage |
| new tests | ✓ 17 in tests/test_services/test_new_sources.py (remotive, ats detect/fetch, yc, targets, config) |
