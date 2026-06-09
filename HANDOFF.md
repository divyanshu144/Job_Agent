# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — uncommitted "profile review" feature in working tree

---

## Current State

An in-flight **profile review** feature is sitting uncommitted on `main` (not authored in the
current session). It adds review state to the `Profile` model (`profile_review_data`,
`review_status`, `reviewed_at`), backed by a new Alembic migration
`0002_add_profile_review_fields.py`, plus supporting changes across `profile_builder`,
`orchestrator`, `routes/profile`, `routes/history`, and `schemas`. Frontend adds a new
`AdminInvites.tsx` page, a much-expanded `ProfileSetup.tsx`, and invite-token wiring in
`Register.tsx`. Tests for the new behaviour are present (profile, history, auth, migrations,
profile_builder, sse_sequence). Nothing has been committed yet.

## Next Action

Decide whether to commit this feature. If yes: run `make check` to confirm green, then commit the
profile-review changes as one logical unit (model + migration + routes + schemas + services +
frontend + tests). The last commit is `1b50f59 feat: support docx resumes and tighten access`.

## Why It Stopped

Natural end of an unrelated session (a `claude update` request). The dirty tree is pre-existing
in-flight work; HANDOFF.md was refreshed to reflect actual working-tree state so it matches reality.

## In-Flight

Modified:
- backend/models.py, backend/routes/history.py, backend/routes/profile.py, backend/schemas.py
- backend/services/orchestrator.py, backend/services/profile_builder.py
- frontend/src/App.tsx, frontend/src/api/client.ts, frontend/src/pages/ProfileSetup.tsx,
  frontend/src/pages/Register.tsx, frontend/src/pages/Results.tsx, frontend/src/types/index.ts
- tasks/agent_memory.md
- tests/test_database.py, tests/test_migrations.py, tests/test_orchestrator/test_sse_sequence.py,
  tests/test_routes/test_history.py, tests/test_routes/test_profile.py,
  tests/test_services/test_profile_builder.py, tests/test_startup.py

Untracked:
- alembic/versions/0002_add_profile_review_fields.py
- frontend/src/pages/AdminInvites.tsx
- tests/test_routes/test_auth.py

## Open Questions

- Is the profile-review feature ready to commit, or still mid-implementation? (No prior HANDOFF
  context described it; reconstructed from the diff.)

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | Not run this session |
| `make lint` | Not run this session |
| `make check` | Not run this session |
