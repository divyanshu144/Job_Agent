# Design: Sentry error alerting for JobFit

**Date:** 2026-07-08
**Status:** Approved design, pre-implementation
**Scope decision:** Single focused subsystem — one spec, one plan.

## Problem

At 5–10 active users, pipeline failures are invisible until a user reports them.
Today a failing agent is caught at the orchestrator `except` sites, logged via
`logger.exception(...)`, converted to a user-safe string by `to_user_error()`, and
emitted as a `pipeline_error` SSE event. The stack trace lands in CloudWatch logs
that nobody watches. There is no alert, no aggregation, no "this agent has failed
12 times for 3 users in the last hour." We need push alerting with enough context
to act without SSHing into logs.

## Goal

Send handled pipeline failures **and** genuinely unhandled exceptions (API 500s,
Celery task crashes) to Sentry (org `student-ixx`, project `Jobfit-api`), each
tagged so issues are filterable by environment, component, agent, pipeline phase,
and (hashed) user. No resume/JD/CV content ever reaches Sentry.

## Key design decision: capture at the `except` sites, not the SSE emit

The `pipeline_error` SSE event is **deliberately sanitized** — `to_user_error()` is
the single boundary and its `message` never contains `str(exc)` (see
`tasks/agent_memory.md → Architecture Decisions`). Capturing there would send Sentry
a generic string with no stack trace, no exception type — useless for debugging.

Instead we capture the **raw exception** at the three orchestrator `except` blocks,
co-located with the existing `logger.exception(...)` calls, where `e` is still in
scope:
- `orchestrator.py:256` — Phase-1 non-streaming helper
- `orchestrator.py:390` — Phase-1 streaming path
- `orchestrator.py:512` — Phase-2 streaming step (`_tracked`)

The SSE contract to the browser is **unchanged**. Sentry capture is additive.

On top of that, Sentry's FastAPI + Celery integrations auto-capture *unhandled*
exceptions for free (a route that 500s, a task that raises past its handler). The
pipeline errors above are *handled/swallowed*, so they need the explicit capture;
everything else the integrations catch automatically.

## Scope

**In scope**
- `sentry-sdk` dependency (with the FastAPI + Celery extras it needs).
- New `backend/services/sentry.py`: `init_sentry(component)`, `capture_pipeline_error(...)`,
  a `before_send` scrubber, and a stable user-id hash helper.
- Fork-safe init: API in `main.py` lifespan; Celery workers via the
  `worker_process_init` signal (fires *inside each forked child*); Celery beat via
  the `beat_init` signal.
- Explicit `capture_pipeline_error(...)` at the three orchestrator `except` sites.
- A `retry_count` counter on `BaseAgent` (reset per `run()`), read off the agent
  instance at the except site — the retry count is not otherwise a scalar in scope.
- `SENTRY_DSN` threaded exactly like existing secrets: `settings.sentry_dsn`, a new
  SSM parameter, and a `secrets[]` entry in the api/worker/beat task-definitions.
- Tag scoping: environment, component, agent, phase, error code, retry count, hashed user.

**Out of scope (deferred, tracked)**
- Performance tracing / spans (`traces_sample_rate=0` — errors only).
- Release health, source maps, frontend (browser) Sentry.
- Slack/email routing rules (configured in the Sentry UI, not code).
- Alerting on discovery/campaign background paths beyond what the Celery integration
  catches for free (they already run under the worker, so unhandled crashes are covered;
  no explicit pipeline-style capture is added for them in this phase).

## Components

### `backend/services/sentry.py` (new)

```python
def init_sentry(component: str) -> None:
    """Idempotent. No-op when settings.sentry_dsn is empty (local dev + tests).
    component is one of 'api' | 'worker' | 'beat' — attached as a global tag so
    every event is filterable by which process produced it."""
```
- Reads `settings.sentry_dsn`; empty → return immediately (Sentry stays uninitialised,
  so tests and local dev never emit).
- `environment=settings.app_env` (development / staging / production).
- Integrations: `FastApiIntegration`, `StarletteIntegration`, `CeleryIntegration`.
- `traces_sample_rate=0.0` (errors only), `send_default_pii=False`,
  `max_request_body_size="never"` (never attach request bodies — they carry JD text).
- `before_send=_scrub` (see below). Sets the global `component` tag.
- Idempotency: guard with a module-level `_INITIALISED` flag so a re-entrant call
  (e.g. lifespan re-run in tests) is a no-op.

```python
def capture_pipeline_error(
    exc: BaseException, *, agent: str, phase: str,
    user_id: str | None, retry_count: int, error_code: str,
) -> None:
    """Send a handled pipeline exception to Sentry with pipeline context tags.
    No-op when Sentry is uninitialised. Never raises — capture must not turn a
    handled agent failure into an unhandled one (fail-open, like _log_retry)."""
```
- Opens an isolated scope (`sentry_sdk.new_scope()`), sets tags:
  `agent`, `phase` (`phase1` | `phase2`), `error_code`, `retry_count`,
  `user=<hashed>`, and `trace_id=get_trace_id()` (correlates with our JSON logs).
- Calls `sentry_sdk.capture_exception(exc)`.
- Wrapped in `try/except Exception` → swallowed (fail-open).

```python
def _hash_user_id(user_id: str | None) -> str | None:
    """Stable, non-reversible correlation id: sha256(user_id) hex, first 12 chars.
    For grouping issues by user without storing the raw id. Not a security control."""
```

```python
def _scrub(event, hint):
    """before_send hook. Defence in depth: drop request body/cookies/headers and any
    top-level PII keys before the event leaves the process. Returns the event or None."""
```
- Removes `event["request"]` body/cookies/headers if present.
- Belt-and-braces given we already set `send_default_pii=False` +
  `max_request_body_size="never"`; the scrubber is the guarantee that a future
  integration change can't silently start leaking JD/CV/profile content.

### `BaseAgent.retry_count` (modify `backend/agents/base.py`)

- Add `self._retry_count: int = 0` in `__init__`.
- Reset to `0` at the top of `run()`.
- Increment on each outer-retry attempt (in the `AsyncRetrying` path) and on each
  self-correction retry (`_log_retry`), so it reflects total retries the agent
  burned before the exception propagated.
- Expose as a read-only `retry_count` property.
- Rationale: the orchestrator holds the `agent` instance in scope at the except site
  (`for agent_name, agent in ...`), so it can read `agent.retry_count` directly — no
  DB query on the error path, no new parameter threading.

### Init wiring

- **API** — `backend/main.py` `lifespan()`: call `init_sentry("api")` as the first
  line, before `configure_logging()`. (Init before logging so any config-time error
  is captured.)
- **Worker** — `backend/celery_app.py`: connect a `worker_process_init` handler that
  calls `init_sentry("worker")`. This fires in each forked child *after* the fork, so
  the Sentry background transport thread is created in the child — fork-safe. Do **not**
  init at module import (that would create the transport in the parent, pre-fork).
- **Beat** — same module: connect a `beat_init` handler calling `init_sentry("beat")`.
  Beat is a single scheduler process (no fork), so this simply catches scheduler crashes.

### Orchestrator capture (modify `backend/services/orchestrator.py`)

At each of the three `except Exception as e:` blocks, immediately after
`logger.exception(...)` and after computing `ue = to_user_error(name, e)`:

```python
capture_pipeline_error(
    e, agent=name, phase=<"phase1"|"phase2">,
    user_id=user_id, retry_count=agent.retry_count, error_code=ue.code,
)
```
- `phase` is a literal per call site (the two Phase-1 sites pass `"phase1"`, the
  Phase-2 `_tracked` site passes `"phase2"`).
- Where the agent instance isn't in local scope at a given site, pass `retry_count=0`
  (the plan will confirm scope per site and thread the instance if it is available).
- No behaviour change to the SSE emit, `upsert_job_result`, or `partial` handling.

## Data flow

```
agent.run() raises
  → except site: logger.exception (unchanged)
  → to_user_error(e) → ue  (unchanged)
  → capture_pipeline_error(e, agent, phase, user_id, agent.retry_count, ue.code)
        → new isolated scope + tags (hashed user, trace_id, agent, phase, code, retries)
        → sentry_sdk.capture_exception(e)  [no-op if DSN unset]
  → SSEEvent("pipeline_error", {user-safe message})  (unchanged)
```
Unhandled route/task exceptions bypass this entirely and are caught by the
FastAPI / Celery integrations.

## Config & secrets

- `backend/config.py`: add `sentry_dsn: str = ""`. Empty default → disabled locally
  and in tests. Read only through `settings`, per project convention.
- **SSM parameter** (new): `/jobfit/staging/sentry-dsn` holding the ingest DSN
  (real value lives only in SSM — never in this repo).
  The DSN is a write-only ingest key, but we thread it through SSM like every other
  secret for consistency with the existing pattern (never committed, never in a
  task-def `environment` block).
- **Task definitions** — add to the `secrets[]` array of `api.json`, `worker.json`,
  and `beat.json`:
  ```json
  { "name": "SENTRY_DSN", "valueFrom": "arn:aws:ssm:eu-west-2:896476315730:parameter/jobfit/staging/sentry-dsn" }
  ```
- `.env.example`: add a commented `SENTRY_DSN=` placeholder (no real value).
- `infra/aws/README.md`: list `SENTRY_DSN` alongside the other SSM-backed secrets.

## Tag scoping (filterable in Sentry)

| Tag | Source | Example |
|-----|--------|---------|
| `environment` | `settings.app_env` | `staging` |
| `component` | init arg | `api` / `worker` / `beat` |
| `agent` | except-site agent name | `match_scorer` |
| `phase` | except-site literal | `phase1` / `phase2` |
| `error_code` | `ue.code` | `rate_limited` |
| `retry_count` | `agent.retry_count` | `2` |
| `user` | `_hash_user_id(user_id)` | `9f2ac1b0e3d4` |
| `trace_id` | `get_trace_id()` | `<hex>` |

## Testing (Definition of Done)

- `init_sentry`: no-op when `sentry_dsn == ""` (assert `sentry_sdk.Hub.current.client is None`
  / no client bound); when set (monkeypatched DSN + recording transport), binds a client
  with `environment == app_env` and the `component` tag.
- `_hash_user_id`: stable across calls, 12-char hex, differs for different ids, `None → None`.
- `_scrub`: an event carrying `request.data`/cookies/headers comes back with those removed;
  returns the event otherwise.
- `capture_pipeline_error`: with a recording transport, a raised exception produces one
  event whose tags include the expected `agent`, `phase`, `error_code`, `retry_count`,
  hashed `user`, and `trace_id`; assert **no** raw `user_id`, JD, profile, or CV text
  anywhere in the serialised event. With Sentry uninitialised it is a silent no-op and
  never raises.
- `BaseAgent.retry_count`: `0` after a clean `run()`; increments across outer-retry and
  self-correction attempts; resets at the start of the next `run()`.
- Orchestrator wiring: patch `capture_pipeline_error`; drive a failing agent through each
  of the three paths and assert it's called once with the right `agent`, `phase`, and
  `error_code` — and that the `pipeline_error` SSE event is still emitted unchanged.
- Celery signals: assert `worker_process_init` and `beat_init` handlers are connected and
  call `init_sentry` with the right component (patch `init_sentry`, send the signal).
- `make check` green (fmt + lint + mypy + schema-drift + tests, `--cov-fail-under=70`).
  No schema exposed to TS → no schema-drift impact expected.

## Rollout

1. Put the DSN in SSM (`/jobfit/staging/sentry-dsn`) before deploy.
2. Register the updated task-definitions (api/worker/beat) so the secret is injected.
3. Deploy. No DB migration required.
4. Smoke test in prod: trigger a deliberate agent failure (e.g. a JD that forces an
   invalid-output path, or temporarily point an agent at a bad model) and confirm the
   event appears in the `Jobfit-api` project with the expected tags and **no** PII.
5. Configure alert routing (Slack/email) in the Sentry UI — out of code scope.
- Ships as a patch release (`v1.3.2`).

## Open questions (resolved)

- Capture point → **the three orchestrator `except` sites** (raw exception), not the
  sanitized SSE emit. ✅
- Handled vs unhandled → **both**: explicit capture for swallowed pipeline errors,
  FastAPI/Celery integrations for unhandled. ✅
- PII → **scrubbed**: hashed user id only; `send_default_pii=False` +
  `max_request_body_size="never"` + `before_send` scrubber; no JD/CV/profile. ✅
- Tracing → **errors only** (`traces_sample_rate=0`). ✅
- Retry count → **new `BaseAgent.retry_count`** read off the agent instance at the
  except site (no DB query on the error path). ✅
- Fork safety → **`worker_process_init`** (workers) + **`beat_init`** (beat), never
  module-import init. ✅
- DSN handling → **SSM parameter + task-def `secrets[]`**, like every other secret. ✅
