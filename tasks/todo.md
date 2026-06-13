# TODO — FDE readiness goal (5 tasks)

## Task 0 — Housekeeping — DONE
- [x] commit docs/architecture-review/ (`e99e37d`), push all (origin/main current)

## Task 1 — Health checks + Prometheus metrics — DONE (`cea8f44`, 452 passed, 81.67%)

- [ ] 1. requirements.txt: add `prometheus-fastapi-instrumentator>=7.0.0`
- [ ] 2. `backend/main.py` /health: inject `db: AsyncSession = Depends(get_db)`,
      `await db.execute(text("SELECT 1"))` →
      200 `{"status":"ok","db":"ok"}` / 503 `{"status":"degraded","db":"error","detail":<exc type name>}`
      (detail = exception class name only — never raw str(exc), per project error-boundary rule)
- [ ] 3. `backend/main.py`: `Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)`
      → per-route latency histogram + status-code counters (error rate). Root path; no clash
      with `/api/metrics/*` cost routes.
- [ ] 4. `backend/services/instrumentation.py`: module-level
      `LLM_CALLS = Counter("llm_calls_total", ..., ["agent", "model"])`,
      incremented in `tracked_call` after the API call returns (real API calls only —
      cache hits and batch results excluded by design)
- [ ] 5. TDD: `tests/test_routes/test_health.py` (200 healthy; 503 degraded via failing
      get_db override), `/metrics` exposure test, llm_calls_total increment test in
      `tests/test_services/test_instrumentation.py`
- [ ] 6. make check green → commit

Known limitation (accepted, documented): Celery worker LLM calls won't appear in the
API process's /metrics (separate process; multiprocess mode out of scope V1).

## Task 2 — Tenacity retry + breaker signal — DONE (`68f7201`, 459 passed, 81.87%)

- [ ] 1. requirements.txt: add `tenacity>=8.2.0`
- [ ] 2. `backend/agents/base.py` `_call()`: wrap `tracked_call` in `AsyncRetrying(
      stop_after_attempt(3), wait_exponential_jitter(initial=1, max=4), reraise=True)`
      with predicate: APIStatusError AND status_code == 529, httpx.TimeoutException,
      or anthropic.APITimeoutError (SDK wraps httpx timeouts — without it the
      httpx match is dead code). All other exceptions raise immediately, once.
- [ ] 3. Breaker signal: module-level consecutive-failure counter in base.py;
      any _call failure (post-retry) increments, success resets; CRITICAL log
      exactly when streak hits 5 (once per streak, no spam).
- [ ] 4. No orchestrator changes; AgentError/to_user_error mapping untouched;
      reraise=True keeps original exception types for the error boundary.
- [ ] 5. TDD: tests/test_agents/test_base_retry.py — 529 retried then succeeds;
      400 not retried; timeout retried; exhaustion re-raises original; breaker
      CRITICAL at 5 consecutive; success resets streak. Monkeypatch module-level
      `_RETRY_WAIT` to wait_none() for fast tests.
- [ ] 6. make check green → commit

Noted: SDK already retries 429/5xx internally (anthropic_max_retries) — tenacity
is the OUTER layer for when the SDK gives up; worst-case latency multiplies
(intentional per spec).
## Task 3 — Unit 8 campaign frontend dashboard — DONE (`5a9de23`, build clean, drift 11 classes)

Frontend only. Endpoints used (all exist): POST /campaign/run-now, GET /campaign/runs,
GET/POST/PATCH/DELETE /targets, GET /history (materials), /results/:id (links).

- [ ] 1. types/index.ts: `CampaignRun` (mirrors CampaignRunResponse),
      `TargetCompany` (mirrors TargetCompanyResponse)
- [ ] 2. api/client.ts: runCampaignNow, getCampaignRuns, getTargets, addTarget,
      updateTarget, deleteTarget (get/post/put helpers + patch/delete additions
      following existing style)
- [ ] 3. pages/Campaign.tsx: run-now button (409 → friendly inline banner),
      active-run polling (Discover pollRef pattern: 3s interval, max attempts,
      clear on terminal status, timed-out banner + manual refresh), run history
      (newest first: status badge, timestamps, considered/drafted/failed, error),
      targets management (list + add form name/ats-select/slug + active toggle +
      delete), recent materials via listHistory → /results/:id links
- [ ] 4. App.tsx: /campaign route + NavLink (all authenticated users, NOT admin-gated)
- [ ] 5. scripts/check_schema_drift.py: add (CampaignRunResponse, CampaignRun) +
      (TargetCompanyResponse, TargetCompany) pairs
- [ ] 6. Verify: make check green + frontend tsc/vite build clean → commit

GAPS (listed, not invented):
- No GET/PATCH /campaign/settings route → settings section omitted (enabled
  toggle + caps not displayable without inventing a backend route)
- CampaignRunResponse has no cost field → run history shows counts only
- No user-scoped CampaignJob endpoint; regular-tier runs produce Analyses, not
  CampaignJobs → "drafts" section = recent analyses from /history
## Task 4 — Consistency evals — ALREADY ON MAIN (no-op)
Commit `3c39fe0` (feat/evals-clean's content) is in main history: validators.py,
consistency_check.py, tests/test_evals (33 pass), make eval-consistency target.
Branch deleted after a prior integration. Nothing to merge.

## Task 5 — Rate limiting (slowapi) — DONE (`f56a443`, 466 passed, 82.08%)

- [ ] 1. requirements.txt: slowapi>=0.1.9
- [ ] 2. backend/services/rate_limit.py: key_func = "user:{jwt sub}" from the
      access_token cookie when decodable, else "ip:{remote addr}";
      Limiter(default_limits=["100/minute"], headers_enabled=True)
- [ ] 3. main.py: app.state.limiter + RateLimitExceeded handler (429 with
      Retry-After) + SlowAPIMiddleware; /health exempted (@limiter.exempt);
      /metrics stays under default (scrape rate trivially low)
- [ ] 4. routes/auth.py: @limiter.limit("10/minute", key_func=remote address)
      on register + login (per-IP, counts failed attempts); both gain a
      request: Request param (slowapi requirement)
- [ ] 5. conftest.py: autouse fixture disables the limiter suite-wide (the whole
      suite shares one fake user — 100/min would 429 the suite); dedicated
      rate-limit tests re-enable + limiter.reset()
- [ ] 6. TDD tests/test_routes/test_rate_limit.py: 11th login from same IP → 429
      + Retry-After; 101st authenticated request → 429; /health exempt; headers
- [ ] 7. make check green → commit

Known limitation: in-memory storage = per-process counters (multi-worker /
Celery not shared). Redis storage_uri is the V2 upgrade if needed.

## Review fixes (2026-06-12) — 10 findings from whole-code review
- [ ] 1+2. orchestrator: _find_cached helper — user-scoped (user_id or NULL),
      newest-first limit 1 (kills cross-tenant hit + MultipleResultsFound)
- [ ] 3. models+0007: partial unique index one running CampaignRun per user;
      enqueue catches IntegrityError → None
- [ ] 4. enqueue: stale-running self-heal (>30 min → failed); .delay() failure
      marks run failed + raises; route 503; dispatcher isolates per-user failures
- [ ] 5. main.py: CRITICAL log at startup when jwt_secret is the published default
- [ ] 6+8. client.ts ApiError(status); Campaign.tsx branches on 409 status,
      poll tolerates 429 (skip tick, keep polling)
- [ ] 7. models+0007: index llm_calls(user_id, created_at)
- [ ] 9. usage.get_or_create_settings: IntegrityError → rollback + re-select
- [ ] 10. execute_campaign_run: cap-stop reason recorded on completed run
- [ ] tests: cache scoping/dup, enqueue stale+queue-failure, run reason,
      jwt guard, startup head 0007; make check + npm build green

## Second review round fixes (2026-06-13)
- [x] BATCH 1 (`3fa0eb9`): #1 tenant boundary (refuse, zero-spend, admin-only
      fallback, starter profile on GET, own-data refresh) + #6 already_generated
- [x] BATCH 2 (`a4f733b`): #2 non-running run no-op, #3 dispatch rollback,
      #4 stamp-to-matching-revision (0006 when 0007 indexes missing)
- [ ] LATER cleanup pass (per user): #5, #7, #8, #9, #10 — untouched
