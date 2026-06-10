# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — supervised live run in progress; pipeline proven on one job

---

## Current State

The pipeline now runs **end-to-end against real services** (the long-standing gate
is cleared). Docker is the run environment: app image has texlive + an `./assets`
volume mount; `.env` carries all creds (incl. a de-spaced `GMAIL_CLIENT_ID`).

A bounded single-job trace (Stripe role, via `docker compose exec`) went
`discovered → scored → résumé compiled → contact found (Hunter) → cold email →
Gmail draft` successfully (one `drafted` CampaignJob). Two content fixes were then
shipped and **verified live in the rebuilt container**:
- résumé tailoring constrained to **one page** (`resume_latex._SYSTEM`),
- résumé + cold email **humanized, em/en dashes banned** across all three content
  prompts. Verified: tailored résumé 1 page, zero AI-introduced dashes (the 5 `---`
  left are pre-existing in the user's own base résumé), cold email dash-free and
  human-toned.

`target_companies.json` curated: Stripe removed (its 499 mostly-sales listings made
it a poor first batch); now Netlify / Ramp / Vercel / Linear.

## Next Action

Run a real small-batch campaign: confirm the curated targets, then trigger
discovery for `source="targets"` (produces `scored` jobs) followed by
`run_campaign(threshold=0.75)`. Watch `/api/campaign/status`. Or first clean up the
trace's leftover rows + the test Gmail draft.

## Why It Stopped

Verification complete; awaiting the call on scope of the first real `run_campaign`.

## In-Flight

No uncommitted changes after this commit. Real artifacts from the trace: one Gmail
draft (Stripe "Account Executive, AI Sales") in the user's Drafts — may want to
delete; one Hunter credit spent; leftover dev-DB rows (DiscoveryRun/Job/Analysis/
CampaignJob=drafted/Contact) — harmless, that Job won't be re-processed.

## Open Questions

- Scope/threshold for the first real `run_campaign`?
- Strip the 5 `---` from the user's base `resume.tex`? (their file; their call)

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | ✓ 393 passed, 1 deselected · 80.15% |
| `make lint` | ✓ clean |
| live single-job trace | ✓ end-to-end (drafted); 1-page + dash-free verified post-rebuild |
