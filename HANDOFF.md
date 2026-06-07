# Session Handoff

**Updated:** 2026-06-07
**Branch:** feat/campaign-orchestrator (off `main`) — committed, not yet merged/pushed

---

## Current State

**Prompt 2 COMPLETE — CampaignJob model + campaign orchestrator skeleton + Alembic introduced.**
TDD (5 tests written failing first, then implemented). `make check` green (**259 passed, 77.89%
cov**); ruff + mypy + schema-drift pass.

**What landed:**
- **Alembic introduced** (hybrid): `create_all`/`init_db` stays as the fresh-DB + test bootstrap;
  Alembic is the forward-migration tool for deployed DBs. Files: `alembic.ini`, `alembic/env.py`
  (async; URL from `settings.database_url` unless a caller overrides via `set_main_option`),
  `alembic/script.py.mako`, `alembic/versions/0001_add_campaign_jobs.py` (hand-authored). `alembic`
  added to `requirements.txt`. Baseline: deployed DBs → `alembic upgrade head`; fresh → create_all
  then `alembic stamp head`.
- **`CampaignJob` model** (`backend/models.py`): id, job_id (FK jobs), run_at, match_score
  (Float, **nullable** — 0–1), draft_id, status (queued|drafted|failed), error, created_at.
- **`backend/services/campaign_orchestrator.py`**: `run_campaign(threshold=0.75) -> CampaignRunResult`
  — pulls `Job.state=="scored"` not already in campaign_jobs; `_score_job` (job_parser→match_scorer,
  returns score/100) per job; filters `>= threshold`; inserts `CampaignJob(status="queued")`; calls
  4 **stub** no-ops (`_cover_letter`, `_resume_tailor`, `_contact_find`, `_draft_create` — log TODO,
  return None). **Each job in its own `SessionLocal()`**; per-job errors → `status="failed"`,
  `error=str(e)`, continue (recorded in a fresh session).

**Verified:** unit tests (queue/skip/dedupe/failure-isolation/stub-noop) + migration test
(`tests/test_migrations.py` runs `command.upgrade` on a temp DB) + manual `alembic upgrade head` on a
copy of `data/jobfit.db` → `campaign_jobs` created with FK to real `jobs`.

## Next Action

Merge `feat/campaign-orchestrator` → `main` + push (on your go), then **Prompt 3** (implement the
first stub step). The stubs are the designed seams: each currently logs TODO and returns None.

## In-Flight

Committed on `feat/campaign-orchestrator`: `backend/models.py`,
`backend/services/campaign_orchestrator.py`, `alembic/*`, `alembic.ini`, `requirements.txt`,
`tests/test_services/test_campaign_orchestrator.py`, `tests/test_migrations.py`, this HANDOFF.

## Open Questions

1. Merge/push this branch now, or stack Prompt 3 on it first?
2. `feat/job-board-scrapers` + `feat/referral-clean` still linger (unmerged) from the cleanup pass.
3. Stub order/return contract for Prompt 3: which step first, and does each return an id/artifact the
   next consumes (e.g. draft_create → draft_id on the CampaignJob)?

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 259 passed, 1 deselected, 77.89% coverage |
| migration | ✓ test_migrations upgrade head creates campaign_jobs; smoke on real-DB copy passed |
