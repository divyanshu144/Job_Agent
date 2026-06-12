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

## Task 2 — Tenacity retry + breaker signal in BaseAgent._call() (PLAN — awaiting approval)

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
## Task 3 — Unit 8 campaign frontend dashboard (plan after task 2)
## Task 4 — Consistency evals merge from feat/evals-clean
## Task 5 — Rate limiting (slowapi)
