# Session Handoff

**Updated:** 2026-06-07
**Branch:** feat/campaign-draft (off `feat/resume-latex`) — committed, not merged/pushed

---

## Current State

**Prompt 5 COMPLETE — `_draft_create` (Gmail draft) is the real terminal step.**
TDD (4 tests: 3 new draft tests + the order test extended). `make check` green (**270 passed,
77.93% cov**); ruff + mypy + schema-drift pass. The campaign pipeline now runs end-to-end:
`score → resume PDF → contact → cold email → Gmail draft`.

**What landed (`campaign_orchestrator.py`):**
- **`_draft_create(job_id, pdf, contact, email, db) -> str`** — builds a multipart MIME message
  (To = `contact.email` or blank; Subject/body = the cold email text; PDF attached as
  `application/pdf`, filename `{company}_resume.pdf`), base64url-encodes it, and calls
  `gmail.users().drafts().create(userId="me", body={"message": {"raw": …}})`. On success →
  `CampaignJob.draft_id` set, `status="drafted"`. On Gmail error → `status="failed"`, `error=str(e)`,
  returns `""` **without raising** (run continues). `run_campaign` counts a job by the returned draft
  id (truthy → queued, "" → failed).
- **Gmail client** (`_gmail_client`, `# pragma: no cover`): **server-side `google-api-python-client` +
  `google-auth` with an OAuth refresh token from settings — NOT the Claude.ai Gmail MCP** (which is
  unavailable server-side). Factored out so tests mock it. Helpers `_build_message` / `_encode` /
  `_create_draft` (blocking call run via `asyncio.to_thread`) / `_set_campaign_status`.
- **config**: `gmail_client_id`, `gmail_client_secret`, `gmail_refresh_token` (env).
- **requirements**: `google-api-python-client`, `google-auth`.

**Testing:** Gmail client fully mocked — assert MIME shape (multipart + PDF attachment + filename),
blank To when contact is None, draft_id captured + status flipped to drafted, and Gmail failure →
status=failed without aborting the run. No network in CI.

## Next Action

Pipeline is functionally complete (score → resume → contact → email → draft). Likely next:
(a) a route/trigger for `run_campaign`, (b) Discover.tsx source toggles (still deferred), (c) the
deferred decision to actually **send** drafts vs leave as Gmail drafts for human review. Then merge
the campaign chain to `main` + push.

## In-Flight

Committed on `feat/campaign-draft`: `backend/services/campaign_orchestrator.py`, `backend/config.py`,
`requirements.txt`, `tests/test_services/test_campaign_orchestrator.py`, this HANDOFF. Stacks:
`feat/campaign-orchestrator` (P2) → `feat/resume-latex` (P3) → `feat/campaign-draft` (P4+P5). None on
`main` yet.

## Open Questions

1. **Merge the campaign chain to `main` + push** — 4 stacked branches (P2→P5) ready; when?
2. Send vs draft-only: drafts are created for human review (gmail.compose scope). Auto-send later?
3. Real `assets/resume.tex`, real `target_companies.json` slugs, and Gmail OAuth creds in `.env` are
   needed for a live run.
4. `feat/job-board-scrapers` + `feat/referral-clean` still linger from the cleanup pass.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 270 passed, 1 deselected, 77.93% coverage |
| new tests | ✓ MIME+attachment / blank-To / draft-id+status / Gmail-failure-no-raise + terminal-order |
| Gmail | client mocked in CI; real runs need google libs + gmail_* env (no MCP) |
