# Architecture Improvement Roadmap

This roadmap is grounded in the current codebase and prioritized for making the project stronger for AI Engineer / Full-Stack AI Engineer interviews.

## Ticket 1: Harden Authentication for Production

Priority: P0

Affected files:

- `backend/config.py`
- `backend/routes/auth.py`
- `backend/services/auth_service.py`
- `tests/test_routes/test_auth.py`
- `tests/test_services/test_auth_service.py`

Why it matters:

The app uses cookie JWT auth. That is acceptable, but production deployment needs secure cookie flags, a non-default JWT secret, and CSRF/Origin protection for mutating routes.

Implementation steps:

1. Add settings such as `environment`, `cookie_secure`, and `allowed_origins` in `backend/config.py`.
2. Add a startup/config validation that rejects the default `jwt_secret` when `environment == "production"`.
3. Set `secure=settings.cookie_secure` on login/register cookies in `backend/routes/auth.py`.
4. Add CSRF token or Origin/Referer validation for mutating cookie-auth requests.
5. Keep local development behavior simple and documented.

Tests to add:

- Production config rejects default JWT secret.
- Login/register set secure cookie when configured.
- Mutating authenticated route rejects invalid CSRF/Origin.
- Existing auth happy-path tests still pass.

Acceptance criteria:

- The app cannot start in production with the default JWT secret.
- Auth cookies are secure in production mode.
- Cookie-auth POST/PATCH/DELETE requests have CSRF or Origin protection.

## Ticket 2: Move Discovery Execution to Celery

Priority: P0

Affected files:

- `backend/services/discovery.py`
- `backend/routes/discovery.py`
- `backend/tasks.py`
- `backend/celery_app.py`
- `backend/models.py`
- Alembic migration if adding task metadata
- `tests/test_routes/test_discovery_routes.py`
- `tests/test_services/test_discovery.py`
- `tests/test_services/test_celery_tasks.py`

Why it matters:

Discovery currently uses in-process `asyncio.create_task()` in `backend/services/discovery.py`. Active runs can be killed by API process restart. Campaigns already use a more production-ready Celery pattern.

Implementation steps:

1. Add Celery tasks such as `discovery.run_source`, `discovery.run_all`, and optionally `discovery.run_batch`.
2. Refactor `_run_discovery_task()`, `_run_all_discovery_task()`, and `_run_batch_discovery_task()` so they can be called from Celery with a fresh task-owned async DB session.
3. Follow the `task_session()` pattern in `backend/tasks.py`.
4. Update routes to create `DiscoveryRun` and enqueue Celery tasks instead of calling `asyncio.create_task()`.
5. Optionally add `task_id` to `DiscoveryRun` through Alembic.
6. Preserve idempotency through `Job.dedup_hash`.

Tests to add:

- Route enqueues the correct Celery task and returns `run_id`.
- Celery task updates `DiscoveryRun.status`.
- Source failure marks per-source status failed.
- Duplicate jobs remain deduped by `dedup_hash`.

Acceptance criteria:

- Discovery work no longer depends on API process lifetime.
- Existing discovery feed behavior remains unchanged.
- Failed source tasks leave durable failure state.

## Ticket 3: Add Database-Enforced JobResult Uniqueness

Priority: P1

Affected files:

- `backend/models.py`
- `backend/services/job_result.py`
- Alembic migration under `alembic/versions`
- `tests/test_services/test_job_result.py`
- `tests/test_orchestrator/test_retry.py`

Why it matters:

The one-row-per-`(analysis_id, agent_name)` invariant is currently enforced in `upsert_job_result()` application logic. The database should enforce it too.

Implementation steps:

1. Add a unique constraint on `job_results.analysis_id, job_results.agent_name`.
2. Write a migration that deduplicates existing rows before adding the constraint.
3. Update `upsert_job_result()` to use database-native upsert where supported, or keep a transaction-safe delete/insert compatible with the constraint.
4. Verify retry behavior still increments `retry_count`.

Tests to add:

- Creating duplicate `JobResult` rows fails at DB level.
- `upsert_job_result()` replaces existing output/error correctly.
- Concurrent retry attempts cannot create duplicate rows.

Acceptance criteria:

- Database enforces the invariant.
- Retry and generation tests pass.
- Result hydration in `backend/routes/history.py` sees at most one row per agent.

## Ticket 4: Enforce Global LLM Cost Caps

Priority: P1

Affected files:

- `backend/services/usage.py`
- `backend/agents/base.py`
- `backend/services/instrumentation.py`
- `backend/services/orchestrator.py`
- `backend/routes/analyse.py`
- `tests/test_services/test_usage.py`
- `tests/test_routes/test_analyse.py`

Why it matters:

Campaign flows check user cost caps, but interactive analysis/generation can still spend for a user. Cost governance should apply globally to user-attributed LLM calls.

Implementation steps:

1. Decide whether cap checks happen before each agent call or before each pipeline phase.
2. Add a user-safe budget-exceeded error type.
3. Ensure `BaseAgent.with_tracking(..., user_id=...)` is used consistently for interactive and campaign paths.
4. Check monthly spend via `user_spend()` before user-attributed calls.
5. Make admin/discovery behavior explicit; discovery currently has admin/null-user cost attribution in parts of the code.

Tests to add:

- Interactive `/api/analyse` is blocked when monthly cap is exceeded.
- Generation is blocked when cap is exceeded after phase 1.
- Blocked calls do not create new `LLMCall` spend rows.
- User receives a safe retry/action message.

Acceptance criteria:

- All regular-user LLM calls respect configured caps.
- Budget blocks happen before Anthropic calls.
- Cost dashboard remains accurate.

## Ticket 5: Add a Versioned LLM Eval Dataset

Priority: P1

Affected files:

- `backend/evals/`
- `tests/test_evals/`
- `scripts/consistency_check.py`
- New dataset files under `tests/fixtures/evals/` or `backend/evals/datasets/`

Why it matters:

The code has validators and consistency tooling, but not a broad golden dataset. Interviewers will care how LLM quality is measured beyond “it seems good.”

Implementation steps:

1. Create 10-20 representative profile/JD fixtures.
2. Define expected score bands for `match_scorer`.
3. Define required extracted skills for `job_parser`.
4. Define forbidden unsupported resume claims for `resume_tailorer`.
5. Add deterministic mocked tests for validators.
6. Add optional integration tests behind the existing `integration` marker for real model checks.

Tests to add:

- `job_parser` outputs required fields for fixture JDs.
- `match_scorer` scores within expected bands.
- `resume_tailorer` omits unsupported claims.
- Consistency variance remains under threshold for selected fixtures.

Acceptance criteria:

- Eval dataset is versioned in repo.
- CI can run deterministic eval tests without Anthropic.
- Real-model evals can be run manually with `-m integration`.

## Ticket 6: Add Playwright Smoke Tests

Priority: P2

Affected files:

- `frontend/package.json`
- New `frontend/playwright.config.ts`
- New `frontend/tests/`
- Possibly test fixtures/mocks

Why it matters:

Backend coverage is broad, but the primary user journey is browser-based and currently lacks visible automated UI tests.

Implementation steps:

1. Add Playwright dependency and scripts.
2. Start backend/frontend test servers in Playwright config or use mocked API routes.
3. Add smoke tests for:
   - login/register page render,
   - protected route redirect,
   - profile page render,
   - analysis form validation,
   - mocked SSE analysis flow,
   - results page render.
4. Add CI-friendly command.

Tests to add:

- `frontend/tests/auth.spec.ts`
- `frontend/tests/analyse.spec.ts`
- `frontend/tests/results.spec.ts`

Acceptance criteria:

- `npm run test:e2e` or equivalent passes locally.
- A mocked SSE stream drives the analysis UI to a completed state.
- Core navigation does not regress silently.

## Ticket 7: Generate TypeScript Types from OpenAPI

Priority: P2

Affected files:

- `backend/schemas.py`
- `frontend/src/types/index.ts`
- `scripts/check_schema_drift.py`
- New generation script
- `Makefile`

Why it matters:

The frontend manually mirrors backend Pydantic schemas. `scripts/check_schema_drift.py` checks only selected classes. Generated types reduce drift and improve developer experience.

Implementation steps:

1. Add a script to export FastAPI OpenAPI JSON.
2. Use an OpenAPI TypeScript generator to produce frontend API/schema types.
3. Replace or gradually migrate `frontend/src/types/index.ts`.
4. Update `make lint` or `make check` to verify generated files are current.
5. Keep hand-written UI helper types only where needed.

Tests to add:

- Script test or CI check that generated types are up to date.
- Existing frontend TypeScript build must pass.
- Existing schema drift script can be removed or narrowed after migration.

Acceptance criteria:

- Backend schema changes produce updated TypeScript types.
- Manual duplicate schema definitions are reduced.
- `make check` catches stale generated types.

## Ticket 8: Add Regular-User Campaign Dashboard

Priority: P2

Affected files:

- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- New or updated pages under `frontend/src/pages/`
- `backend/routes/targets.py`
- `backend/routes/campaign.py`
- `tests/test_routes/test_targets.py`
- `tests/test_routes/test_campaign_runs.py`

Why it matters:

The backend has regular-tier target companies and campaign runs, but the frontend navigation currently emphasizes admin discovery/cost features. A user-facing campaign dashboard would make the newer architecture demonstrable.

Implementation steps:

1. Add API client methods for `/api/targets` and `/api/campaign/runs`.
2. Add a page for target company CRUD.
3. Add a campaign run history panel.
4. Add a "Run now" button that calls `/api/campaign/run-now`.
5. Show blocked/completed/failed states from `CampaignRunResponse`.

Tests to add:

- Route tests already exist; add frontend tests if Playwright is in place.
- Verify regular users can access the UI and admins do not see misleading controls.

Acceptance criteria:

- A regular user can add targets, run a campaign, and see run history from the UI.
- The page uses existing backend routes without new unsupported API behavior.
