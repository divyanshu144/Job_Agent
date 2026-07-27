# Session Handoff

**Updated:** 2026-07-27
**Branch:** main

---

## Current State

**v1.5.0 shipped to production (AWS ECS).** Pushed 51 commits main was ahead by
(resume editor Plans 1–5, profile dashboard redesign, faithful WYSIWYG PDF download)
to `origin/main` (`b1e45b2`), then tagged and pushed `v1.5.0` to trigger `deploy-aws.yml`.

The prior `v1.4.0` deploy (2026-07-20) had failed at the Alembic-migration step with
`ResourceInitializationError: invalid ssm parameters: /jobfit/staging/sentry-dsn` — the
api/worker/beat task defs declare `SENTRY_DSN` as a required SSM `secrets` entry, but that
parameter never existed. Root-caused and fixed this session: created
`/jobfit/staging/sentry-dsn` as a `SecureString` with the real Sentry DSN. The execution
role's SSM policy is path-scoped (`/jobfit/staging/*`) so it covers the new param with no
IAM change. Sentry error alerting is now live in prod (was a no-op with an empty DSN).

Deploy run `30265401119` completed **success**; all four ECS services report
desired=running=1, rollout COMPLETED (api on task def `jobfit-api:35`).

## Next Action

Nothing pending. Optionally verify Sentry is receiving events (trigger a handled pipeline
error and confirm it surfaces in the Sentry `production` environment). Deferred product
follow-ups if resumed: Plan 6 (cover-letter editor mode); wire the profile version-card
"N roles" to pull from resume content instead of the review record.

## Why It Stopped

Task complete — user asked to push + deploy all changes; both done and verified.

## In-Flight

Nothing uncommitted. `origin/main` = `b1e45b2`; tag `v1.5.0` pushed.

## Open Questions

Faithful downloads can now be 2 pages instead of force-fit to one. This is the intended
WYSIWYG trade-off for hand-curated resumes (one-page discipline kept only for the
auto-generated pipeline output). No action needed unless the user wants a one-page cap back.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` (local, pre-push) | 713 passing · 82.88% coverage ✓ |
| Push to `origin/main` | ✓ `b1e45b2` (triggers CI + docker-build) |
| SSM `/jobfit/staging/sentry-dsn` | ✓ created (SecureString), role policy covers it |
| Deploy run `30265401119` (v1.5.0) | ✓ success — migrations ran, 4 services stable |
| ECS services | ✓ api:35 · worker:28 · beat:26 · frontend:25, all running=1 |
