# Session Handoff

**Updated:** 2026-06-08
**Branch:** feat/contacts-gmail-send (off `main`) — committed, not pushed

---

## Current State

**`/contacts/{id}/send` now actually sends via Gmail** (was a 503 stub). `make check` green
(**277 passed, 78.x% cov**); ruff + mypy + schema-drift pass.

- New `backend/services/gmail_service.py` — canonical server-side Gmail: `gmail_client()` (OAuth
  refresh token, `gmail.compose` scope — covers drafts + send; **no MCP**), `build_message`,
  `encode`, `send_message` (`users().messages().send`).
- `routes/contacts.py::send_email`: builds the drafted subject/body into MIME, sends via
  `asyncio.to_thread(gmail_service.send_message, …)`, then sets `contact.status="sent"` +
  `sent_at`. Gmail failure → **503** `{"error":"gmail_send_failed"}` (kept idempotent "already sent"
  early-return + 400 "draft_required").
- Deduped: `campaign_orchestrator._gmail_client` is now `from gmail_service import gmail_client as
  _gmail_client` (campaign tests unchanged — they patch that name).
- Tests: `test_send_dispatches_via_gmail_and_marks_sent` (asserts the sent MIME carries
  recipient+body, status flips), `test_send_503_on_gmail_failure`. Gmail mocked — no network in CI.

**Requires for a real send:** `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` in `.env` (gmail.compose scope).

## Next Action

Push `feat/contacts-gmail-send` for a PR (on your go). Note other unmerged branches in flight:
`fix/cold-email-tone` (human-tone prompt rewrite), and the Postgres work already merged.

## Open Questions

1. Push/merge `feat/contacts-gmail-send` and `fix/cold-email-tone` — when?
2. App-startup schema strategy (create_all vs `alembic upgrade head`) — still flagged in todo.md.
3. Discovery hits Anthropic 429s on the Tier-1 account under bulk "run all" — mitigations offered
   (batch endpoint / lower `_DISCOVERY_CONCURRENCY` / raise tier); none applied yet.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` (real Postgres) | ✓ 277 passed, 1 deselected |
| new send tests | ✓ Gmail send (mocked) marks sent + 503 on failure |
