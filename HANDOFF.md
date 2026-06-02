# Session Handoff

**Updated:** 2026-06-02  
**Branch:** feat/history (stacks on feat/observability → chore/harness-hooks; nothing merged to main yet)

---

## Current State

**Past analysed jobs surfaced on the Analyse page (A scope — visibility only) COMPLETE.**
TDD throughout; `make check` green (**185 passed, 78.39% cov**), frontend `tsc --noEmit` clean.

- Denormalized `role_type` / `company` / `match_score` (nullable) onto `Analysis` (`models.py`) +
  `init_db()` ALTER migration (`database.py`) so the existing `data/jobfit.db` gains them.
- Populated at write-time in `run_evaluate_pipeline` (orchestrator persist block). `AnalysisSummary`
  schema + TS type gained the fields (`/history` returns them; not in schema-drift PAIRS so no gate
  impact).
- `scripts/backfill_analysis_meta.py` — one-time, **user-run**: `backfill_meta` populates the new
  columns from `job_results` JSON; `--claim-orphans` assigns the 2 orphaned pre-auth manual analyses
  (user_id NULL & job_id NULL) to the sole user (or `--email`).
- Frontend (per user revision — **no separate page**): the analysed-jobs list now renders on
  `AnalyseJob.tsx` (loaded on mount via `api.listHistory`, refreshed after each analyse) — role_type ·
  company · score badge · date · partial, JD-snippet fallback, links to `/results/:id`. The
  standalone `History.tsx` page + `/history` route + nav link were removed. The `GET /api/history`
  endpoint stays (the Analyse page consumes it).
- Tests: `test_routes/test_history.py` (+meta, +auth 401), `test_orchestrator/test_analysis_meta.py`,
  `test_services/test_backfill_analysis_meta.py`.

Findings that shaped it: `job_parser` has `company` (often null) + `role_type` (used as the title;
no `title` field exists); the 2 orphaned analyses are both the "Senior Python Engineer — Remote" JD
(role_type Backend Engineer, score 62), confirmed to the user as likely theirs.

## Next Action

1. **USER runs the backfill** to recover the 4 rows (no `make run` was done):
   `python scripts/backfill_analysis_meta.py --claim-orphans`
   (sole user is exeter792@gmail.com; verify the 2 orphans shown earlier are yours first).
2. Commit is on `feat/history`. Decide PR/branch strategy — three stacked branches exist
   (`chore/harness-hooks` → `feat/observability` → `feat/history`); nothing merged to main.
3. (Deferred B) application-tracker status UI + filters.

## Why It Stopped

History feature complete, committed, verified. Clean stopping point.

## In-Flight

Committed on `feat/history`. Working tree clean after commit. `data/jobfit.db` NOT yet
backfilled (intentional — user runs the script).

## Open Questions

1. PR strategy for the three stacked branches (merge order / squash?).
2. When to build the deferred B slice (status tracking + filters).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ **185 passed, 78.39% coverage** (fmt + lint + mypy + schema-drift + pytest) |
| frontend | ✓ `tsc --noEmit` clean |
| backfill on live DB | ⏳ deferred to user (`scripts/backfill_analysis_meta.py`) |
