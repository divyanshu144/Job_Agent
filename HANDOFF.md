# Session Handoff

**Updated:** 2026-06-07
**Branch:** main (synced with `origin/main` @ `2890567`)

---

## Current State

**Campaign chain (P2–P6) MERGED to `main` and pushed.** `make check` green on merged main
(**275 passed, 78.10% cov**); ruff + mypy + schema-drift pass. `main` ↔ `origin/main` in sync (0/0).

The autonomous application campaign is now end-to-end on `main`:
- **P2** `CampaignJob` model + `run_campaign` orchestrator skeleton; **Alembic** introduced (hybrid:
  create_all stays for fresh DBs/tests; revision `0001_add_campaign_jobs`).
- **P3** LaTeX resume tailoring → PDF (`resume_latex.py`; pdflatex + self-correction retry).
- **P4** `_contact_find` (Hunter.io) + `_cold_email` (ColdEmailAgent) wired.
- **P5** `_draft_create` → Gmail draft (cold email + resume PDF attachment) via server-side OAuth
  (google-api-python-client + google-auth; **no MCP**).
- **P6** manual `POST /api/campaign/run` (202, 409-if-running) + `GET /api/campaign/status`.

Pipeline: `POST /campaign/run` → score → resume PDF → contact → cold email → Gmail draft, observable
via `GET /campaign/status`. Drafts are for human review (no auto-send).

## Next Action

Do a **supervised real run**: real `assets/resume.tex`, real `target_companies.json` slugs, Hunter +
Gmail OAuth creds in `.env`, `pip install -r requirements.txt` (google libs) + texlive (pdflatex);
then `POST /api/campaign/run` and watch `GET /api/campaign/status`. After it's clean, consider a
scheduler + persisted run ledger.

## Open Questions

1. **Branch cleanup**: the 5 merged campaign branches (P2–P6) exist locally + on origin — delete them?
   Also `feat/job-board-scrapers` + `feat/referral-clean` still linger from the earlier cleanup pass.
2. Scheduler (deferred until a clean supervised run), send-vs-draft-only, persisted run history.
3. Discover.tsx source toggles still deferred.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` (merged main) | ✓ 275 passed, 1 deselected, 78.10% coverage |
| `main` ↔ `origin/main` | ✓ in sync (0/0) |
| pushed | ✓ main + feat/campaign-{orchestrator,draft,trigger} + feat/resume-latex |
