# Session Handoff

**Updated:** 2026-06-07
**Branch:** feat/campaign-trigger (off `feat/campaign-draft`) — committed, not merged/pushed

---

## Current State

**Prompt 6 COMPLETE — manual campaign trigger + status endpoints (NO scheduler).**
TDD (5 tests written failing first). `make check` green (**275 passed, 78.10% cov**); ruff + mypy +
schema-drift pass.

**What landed (`backend/routes/campaign.py`, registered in `main.py`):**
- **`POST /api/campaign/run`** — fires `run_campaign(threshold=0.75)` as a background
  `asyncio.create_task` (never blocks; a full run is minutes), returns **202** with `{run_id, status}`.
  **409** if a run is already in progress. Concurrency guarded by an in-process `_state["running"]`
  flag set synchronously before the task is created and cleared in the task's `finally`.
- **`GET /api/campaign/status`** — `running` + `last_run_id` + `last_run_started_at` (in-memory,
  best-effort), `CampaignJob` **counts by status** (queued/drafted/failed), and the most recent
  `limit` (default 5) **failed jobs with their error strings** — to debug the supervised run.
- Both require auth (`get_current_user` → 401 without). `main.py` change is purely additive (one
  import + one `include_router`); existing routes untouched.

**Design note:** run state is **in-process** (no `CampaignRun` table) — single-run guard + last-run
info reset on server restart. Fine for the supervised-validation phase; a scheduler / persisted run
ledger is explicitly deferred.

**Testing:** `run_campaign` mocked for route tests — 202+run_id (and the background task runs the
mock + clears the flag), 409 when already running, status counts + recent-failure errors, and auth
required on both endpoints.

## Next Action

The full pipeline is now triggerable + observable. To do a **supervised real run**: provide real
`assets/resume.tex`, real `target_companies.json` slugs, Hunter + Gmail OAuth creds in `.env`, install
`google-*` + texlive, then `POST /api/campaign/run` and watch `GET /api/campaign/status`.
Then merge the campaign chain to `main` + push.

## In-Flight

Committed on `feat/campaign-trigger`: `backend/routes/campaign.py`, `backend/main.py`,
`tests/test_routes/test_campaign.py`, this HANDOFF. Stack: `feat/campaign-orchestrator` (P2) →
`feat/resume-latex` (P3) → `feat/campaign-draft` (P4+P5) → `feat/campaign-trigger` (P6). None on
`main` yet.

## Open Questions

1. **Merge the 5-branch campaign chain (P2→P6) to `main` + push** — when?
2. Scheduler (deferred): after a clean supervised run, add cron/interval triggering of `run_campaign`.
3. Send vs draft-only (drafts created for human review); persisted run ledger if we want history.
4. `feat/job-board-scrapers` + `feat/referral-clean` still linger from the cleanup pass.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 275 passed, 1 deselected, 78.10% coverage |
| new tests | ✓ 202+run_id / 409-when-running / status counts+errors / auth required (run + status) |
