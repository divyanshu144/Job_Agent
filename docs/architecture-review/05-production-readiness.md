# Production Readiness

This document is intentionally critical. The project has strong architecture for a portfolio/interview project, but several items should be fixed before real production use.

## Production Blockers

### Auth Hardening

Affected files:

- `backend/config.py`
- `backend/services/auth_service.py`
- `backend/routes/auth.py`

Current state:

- JWT auth is stored in an `httponly` cookie.
- Default `jwt_secret` is `"change-me-in-production-use-long-random-string"`.
- Cookies are not marked `secure=True`.
- There is no explicit CSRF protection.

Why it matters:

Cookie-authenticated POST routes are vulnerable if deployment assumptions are wrong. A weak JWT secret is a hard production blocker.

Fix:

- Add an environment flag such as `ENVIRONMENT=production`.
- Refuse to start in production with the default JWT secret.
- Set `secure=True` for cookies in production.
- Add CSRF token or Origin/Referer validation for mutating requests.

Acceptance criteria:

- Production config with default JWT secret fails startup.
- Auth tests assert secure cookie behavior under production config.
- Mutating cookie-auth routes reject invalid CSRF/Origin.

### Durable Discovery Execution

Affected files:

- `backend/services/discovery.py`
- `backend/routes/discovery.py`
- `backend/tasks.py`
- `backend/celery_app.py`

Current state:

Discovery uses `asyncio.create_task()` and a module-level `_background_tasks` set. This protects tasks from garbage collection, but not from process restart.

Why it matters:

A production app process restart can kill active discovery runs.

Fix:

- Move discovery run execution to Celery, following the campaign task pattern in `backend/tasks.py`.
- Store Celery task IDs on `DiscoveryRun` or a related table.
- Make job processing idempotent using `dedup_hash`.

Acceptance criteria:

- `POST /api/discovery/run*` enqueues a Celery task.
- Discovery run status survives API process restart.
- Tests verify route enqueue behavior and task finalization.

## Security Issues

### Admin / Regular-User Boundary Clarity

Affected files:

- `backend/routes/discovery.py`
- `backend/routes/contacts.py`
- `backend/routes/metrics.py`
- `backend/routes/campaign.py`
- `frontend/src/App.tsx`

Current state:

Admin-only features include discovery, contacts, cost dashboard, and old supervised campaign. Regular users can use profile, analysis, targets, and `campaign/run-now`.

Why it matters:

The server-side gates are tested, but the product model is evolving and can be confusing.

Fix:

- Document feature tiers.
- Group route tests by tier.
- Make the frontend navigation match the product tiers.

Acceptance criteria:

- Every route is classified as public/authenticated/admin.
- Tests assert expected access for each tier.

## Reliability Risks

### Application-Enforced JobResult Uniqueness

Affected files:

- `backend/models.py`
- `backend/services/job_result.py`
- Alembic migrations

Current state:

`upsert_job_result()` enforces one row per `(analysis_id, agent_name)` in application logic.

Why it matters:

Concurrent writes or future code paths could create duplicate rows unless the database enforces the invariant.

Fix:

- Add a unique constraint on `(analysis_id, agent_name)`.
- Replace delete/insert with DB-native upsert where possible.

Acceptance criteria:

- Database rejects duplicate result rows.
- Retry tests still pass.
- A concurrency test cannot create duplicates.

### SSE Disconnect / Resume Behavior

Affected files:

- `frontend/src/api/client.ts`
- `backend/routes/analyse.py`
- `backend/services/orchestrator.py`

Current state:

If the browser disconnects, already committed state may remain available, but there is no explicit resume protocol.

Fix:

- Add a client recovery path that reloads `/api/analysis/{id}` when an analysis ID is known.
- Optionally add persisted event state or reconnect semantics.

Acceptance criteria:

- UI can recover from a dropped generation stream by reloading persisted analysis state.

## Scalability Concerns

### Discovery Commit Frequency

Affected file:

- `backend/services/discovery.py`

Current state:

Discovery commits frequently while processing each job.

Why it matters:

This is simple and robust for partial progress, but inefficient at scale.

Fix:

- Batch related updates where safe.
- Keep failure boundaries per job.

Acceptance criteria:

- Discovery tests still pass.
- Measured DB commits per job are reduced.

### JSON Text Columns

Affected file:

- `backend/models.py`

Current state:

Several structured fields are stored as text JSON: `Job.sources`, `matched_profiles`, `Analysis.quality_signals`, `DiscoveryRun.source_statuses`, `JobResult.output_json`.

Why it matters:

This is pragmatic, but limits indexing and database-level validation.

Fix:

- For Postgres, consider JSONB columns for queryable fields.
- Normalize high-value fields if they become filter/sort dimensions.

Acceptance criteria:

- Common feed/history queries have appropriate indexes or JSONB indexes.

## Testing Gaps

Current strengths:

- Backend route/service/agent/orchestrator tests are broad.
- Tests use real Postgres via testcontainers in `tests/conftest.py`.
- Admin gate tests exist in `tests/test_routes/test_admin_gating.py`.

Gaps:

- No visible Playwright/browser smoke tests.
- Eval dataset coverage is limited.
- Schema drift checks are partial.

Recommended fixes:

1. Add Playwright tests for login, profile setup, analysis stream, results render.
2. Add a versioned eval dataset for LLM quality.
3. Generate TypeScript types from OpenAPI rather than manually mirroring schemas.

## Prioritized Improvement Roadmap

1. Auth hardening.
2. Move discovery to Celery.
3. Add `JobResult` unique constraint.
4. Enforce global LLM cost caps.
5. Add eval dataset.
6. Add Playwright smoke tests.
7. Generate OpenAPI TypeScript types.
