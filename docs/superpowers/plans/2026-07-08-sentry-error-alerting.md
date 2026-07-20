# Sentry Error Alerting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push handled pipeline failures and unhandled exceptions from the FastAPI app and Celery workers to Sentry, tagged for filtering, with no resume/JD/CV content leaked.

**Architecture:** A single `backend/services/sentry.py` owns init + capture. The API inits in the FastAPI lifespan; Celery inits per-forked-child via `worker_process_init` (and `beat_init` for the scheduler). Raw pipeline exceptions are captured at the orchestrator `except` sites (co-located with `logger.exception`), where the real exception is still in scope — the sanitized `pipeline_error` SSE event is left unchanged. Sentry's FastAPI + Celery integrations catch genuinely unhandled exceptions for free.

**Tech Stack:** Python 3.11, FastAPI, Celery (prefork), `sentry-sdk` 2.x, pytest, ECS Fargate + SSM Parameter Store.

## Global Constraints

- No PII to Sentry: never send JD text, CV text, or profile content; user id is sent only as a stable hash.
- Init flags on every `sentry_sdk.init`: `traces_sample_rate=0.0`, `send_default_pii=False`, `max_request_body_size="never"`, `before_send=_scrub`, `environment=settings.app_env`.
- DSN empty (`settings.sentry_dsn == ""`) → Sentry stays uninitialised: a hard requirement so local dev and the test suite never emit.
- Fork safety: Celery init happens in `worker_process_init` / `beat_init` signal handlers only — never at module import (that creates the transport thread pre-fork).
- Config is read only through `settings` (never `os.environ`); env var is `SENTRY_DSN`; the secret is threaded via SSM + task-def `secrets[]`, never committed and never in a task-def `environment` block.
- `capture_pipeline_error` and `init_sentry` must never raise (fail-open) — a monitoring failure must not turn a handled agent error into an unhandled one, nor break app boot.
- Ships as `v1.3.2` (patch; no DB migration).

---

### Task 1: Add `sentry-sdk` dependency and `sentry_dsn` config field

**Files:**
- Modify: `requirements.txt` (append one line)
- Modify: `backend/config.py:46` (add field after `redis_url`/celery block)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `settings.sentry_dsn: str` (default `""`); the `sentry-sdk` package importable as `sentry_sdk`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_sentry_dsn_defaults_empty():
    from backend.config import Settings

    assert Settings().sentry_dsn == ""


def test_sentry_dsn_reads_env(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.ingest.sentry.io/42")
    from backend.config import Settings

    assert Settings().sentry_dsn == "https://key@example.ingest.sentry.io/42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_sentry_dsn_defaults_empty tests/test_config.py::test_sentry_dsn_reads_env -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'sentry_dsn'`

- [ ] **Step 3: Add the config field**

In `backend/config.py`, immediately after the Celery lines (`celery_result_backend: str = ""`), add:

```python
    # Sentry error alerting. Empty → Sentry disabled (local dev + tests never emit).
    # Threaded through SSM + task-def secrets in prod, like DATABASE_URL.
    sentry_dsn: str = ""
```

- [ ] **Step 4: Add the dependency**

Append to `requirements.txt`:

```
sentry-sdk>=2.0.0,<3.0.0
```

Then install it into the working environment:

Run: `pip install 'sentry-sdk>=2.0.0,<3.0.0'`
Expected: `Successfully installed sentry-sdk-2.x.x`

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_sentry_dsn_defaults_empty tests/test_config.py::test_sentry_dsn_reads_env -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt backend/config.py tests/test_config.py
git commit -m "feat(sentry): add sentry-sdk dependency and sentry_dsn config field"
```

---

### Task 2: PII scrubber and user-id hash helper

**Files:**
- Create: `backend/services/sentry.py`
- Test: `tests/test_services/test_sentry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `_hash_user_id(user_id: str | None) -> str | None` — sha256 hex, first 12 chars; `None → None`.
  - `_scrub(event: dict, hint: dict) -> dict | None` — strips `request` body/cookies/headers; returns the event.

- [ ] **Step 1: Write the failing test**

Create `tests/test_services/test_sentry.py`:

```python
from backend.services import sentry


def test_hash_user_id_stable_and_short():
    h1 = sentry._hash_user_id("user-abc")
    h2 = sentry._hash_user_id("user-abc")
    assert h1 == h2
    assert len(h1) == 12
    assert h1 != "user-abc"


def test_hash_user_id_differs_and_handles_none():
    assert sentry._hash_user_id("a") != sentry._hash_user_id("b")
    assert sentry._hash_user_id(None) is None


def test_scrub_strips_request_data():
    event = {"request": {"data": "SECRET JD TEXT", "cookies": {"c": "1"}, "headers": {"h": "x"}}}
    scrubbed = sentry._scrub(event, {})
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert "headers" not in scrubbed["request"]


def test_scrub_passes_through_event_without_request():
    event = {"message": "boom", "tags": {"agent": "match_scorer"}}
    assert sentry._scrub(event, {}) == event
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_sentry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.sentry'`

- [ ] **Step 3: Create the module with the two helpers**

Create `backend/services/sentry.py`:

```python
"""Sentry error alerting: init + pipeline-error capture, PII-scrubbed.

Disabled when settings.sentry_dsn is empty (local dev + tests never emit).
Capture happens at the orchestrator except sites with the RAW exception; the
user-facing pipeline_error SSE event stays sanitized. Never raises (fail-open):
a monitoring failure must not break app boot or turn a handled agent error into
an unhandled one.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _hash_user_id(user_id: str | None) -> str | None:
    """Stable, non-reversible correlation id for grouping issues by user without
    storing the raw id. Not a security control — just avoids raw ids in Sentry."""
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def _scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """before_send hook. Defence in depth: drop request body/cookies/headers so a
    future integration change can't silently start leaking JD/CV/profile content."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "headers"):
            request.pop(key, None)
    return event
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_sentry.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/sentry.py tests/test_services/test_sentry.py
git commit -m "feat(sentry): PII scrubber and user-id hash helper"
```

---

### Task 3: `init_sentry` and `capture_pipeline_error`

**Files:**
- Modify: `backend/services/sentry.py`
- Test: `tests/test_services/test_sentry.py`

**Interfaces:**
- Consumes: `settings.sentry_dsn` (Task 1); `_hash_user_id`, `_scrub` (Task 2).
- Produces:
  - `init_sentry(component: str, *, transport: Any = None) -> None` — idempotent; no-op when DSN empty. `transport` is a test seam (a callable receiving the event dict); production passes `None` (real transport).
  - `capture_pipeline_error(exc: BaseException, *, agent: str, phase: str, user_id: str | None, retry_count: int, error_code: str) -> None` — no-op when uninitialised; never raises.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_sentry.py`:

```python
import pytest
import sentry_sdk

from backend.services import sentry as sentry_mod


@pytest.fixture(autouse=True)
def _reset_sentry():
    # Each test must start with a DISABLED client, else a prior test's global
    # client leaks in. init(dsn="") binds a disabled client (is_active() False).
    sentry_mod._INITIALISED = False
    sentry_sdk.init(dsn="")
    yield
    sentry_sdk.get_client().close()
    sentry_sdk.init(dsn="")
    sentry_mod._INITIALISED = False


def test_init_noop_when_dsn_empty(monkeypatch):
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "")
    sentry_mod.init_sentry("api")
    assert not sentry_sdk.get_client().is_active()


def test_init_binds_client_with_environment(monkeypatch):
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "https://k@example.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_mod.settings, "app_env", "staging")
    sentry_mod.init_sentry("api", transport=lambda e: None)
    client = sentry_sdk.get_client()
    assert client.is_active()
    assert client.options["environment"] == "staging"


def test_capture_sets_tags_and_hashed_user_no_pii(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(sentry_mod.settings, "sentry_dsn", "https://k@example.ingest.sentry.io/1")
    sentry_mod.init_sentry("worker", transport=events.append)

    sentry_mod.capture_pipeline_error(
        ValueError("raw boom"),
        agent="match_scorer",
        phase="phase1",
        user_id="user-abc",
        retry_count=2,
        error_code="rate_limited",
    )
    sentry_sdk.get_client().flush()

    assert len(events) == 1
    tags = events[0]["tags"]
    assert tags["agent"] == "match_scorer"
    assert tags["phase"] == "phase1"
    assert tags["error_code"] == "rate_limited"
    assert tags["retry_count"] == "2"
    assert tags["component"] == "worker"
    assert tags["user"] == sentry_mod._hash_user_id("user-abc")
    # No raw user id anywhere in the serialised event.
    import json

    assert "user-abc" not in json.dumps(events[0], default=str)


def test_capture_noop_and_silent_when_uninitialised():
    # No init in this test → must not raise and must emit nothing.
    sentry_mod.capture_pipeline_error(
        ValueError("x"), agent="a", phase="phase1",
        user_id=None, retry_count=0, error_code="agent_failed",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_sentry.py -q`
Expected: FAIL — `AttributeError: module 'backend.services.sentry' has no attribute '_INITIALISED'` / `init_sentry`

- [ ] **Step 3: Implement init and capture**

Edit `backend/services/sentry.py`. Replace the import block and append the new functions:

Change the top imports to:

```python
from __future__ import annotations

import hashlib
import logging
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from backend.config import settings

logger = logging.getLogger(__name__)

_INITIALISED = False
```

Append after the existing helpers:

```python
def init_sentry(component: str, *, transport: Any = None) -> None:
    """Initialise Sentry for this process. Idempotent; no-op when DSN empty.

    component is 'api' | 'worker' | 'beat' — a global tag so every event is
    filterable by which process produced it. transport is a test seam; prod
    passes None (real transport). Never raises — boot must not fail on this.
    """
    global _INITIALISED
    if _INITIALISED or not settings.sentry_dsn:
        return
    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
                CeleryIntegration(),
            ],
            traces_sample_rate=0.0,
            send_default_pii=False,
            max_request_body_size="never",
            before_send=_scrub,
            transport=transport,
        )
        sentry_sdk.set_tag("component", component)
        _INITIALISED = True
    except Exception:  # fail-open: never break boot on a monitoring init error
        logger.exception("sentry init failed for component=%s", component)


def capture_pipeline_error(
    exc: BaseException,
    *,
    agent: str,
    phase: str,
    user_id: str | None,
    retry_count: int,
    error_code: str,
) -> None:
    """Send a handled pipeline exception to Sentry with pipeline-context tags.

    No-op when Sentry is uninitialised. Never raises (fail-open) — a monitoring
    failure must not turn a handled agent failure into an unhandled one.
    """
    from backend.services.instrumentation import get_trace_id

    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("agent", agent)
            scope.set_tag("phase", phase)
            scope.set_tag("error_code", error_code)
            scope.set_tag("retry_count", str(retry_count))
            hashed = _hash_user_id(user_id)
            if hashed is not None:
                scope.set_tag("user", hashed)
                scope.set_user({"id": hashed})
            trace_id = get_trace_id()
            if trace_id is not None:
                scope.set_tag("trace_id", trace_id)
            sentry_sdk.capture_exception(exc)
    except Exception:
        logger.exception("sentry capture_pipeline_error failed for agent=%s", agent)
```

Note: `set_tag("component", ...)` uses the global scope so it applies to
integration-captured unhandled events too; the per-error tags use an isolated
`new_scope()` so they don't leak between captures.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_sentry.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/sentry.py tests/test_services/test_sentry.py
git commit -m "feat(sentry): init_sentry + capture_pipeline_error with scoped tags"
```

---

### Task 4: `BaseAgent.retry_count`

**Files:**
- Modify: `backend/agents/base.py` (`__init__`, `_call`, `_call_structured`, add property)
- Test: `tests/test_agents/test_base_retry_count.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BaseAgent.retry_count -> int` — total retries the agent burned (transient SDK retries in `_call` + self-correction retry in `_call_structured`). `0` on a fresh instance; agents are instantiated fresh per request (documented convention), so no explicit per-run reset is needed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents/test_base_retry_count.py`:

```python
import pytest

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError
from backend.schemas import PriorOutputs


class _Tiny(BaseAgent):
    """Minimal agent exercising _call_structured self-correction."""

    def __init__(self, raw_sequence):
        super().__init__()
        self._raw_sequence = list(raw_sequence)
        self._i = 0

    async def _call(self, system: str, user: str) -> str:  # bypass network
        value = self._raw_sequence[self._i]
        self._i += 1
        return value


class _Out(__import__("pydantic").BaseModel):
    ok: bool


def test_retry_count_zero_on_fresh_instance():
    agent = _Tiny(['{"ok": true}'])
    assert agent.retry_count == 0


@pytest.mark.asyncio
async def test_self_correction_increments_retry_count():
    # First raw is bad JSON → one self-correction call → second raw is valid.
    agent = _Tiny(["not json", '{"ok": true}'])
    out = await agent._call_structured("sys", "user", _Out, label="tiny")
    assert out.ok is True
    assert agent.retry_count == 1


@pytest.mark.asyncio
async def test_double_failure_still_counts_one_self_correction():
    agent = _Tiny(["not json", "still not json"])
    with pytest.raises(AgentError):
        await agent._call_structured("sys", "user", _Out, label="tiny")
    assert agent.retry_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents/test_base_retry_count.py -q`
Expected: FAIL — `AttributeError: 'BaseAgent' object has no attribute 'retry_count'`

- [ ] **Step 3: Implement the counter**

In `backend/agents/base.py` `__init__`, add after `self._prompt_version = None`:

```python
        self._retry_count = 0
```

Add a property (place it just after `__init__`, before `with_tracking`):

```python
    @property
    def retry_count(self) -> int:
        """Total retries this agent burned before returning/raising: transient SDK
        retries (in _call) + self-correction retries (in _call_structured). Fresh
        per request because agents are instantiated fresh per request."""
        return self._retry_count
```

In `_call_structured`, in the `except (json.JSONDecodeError, ValidationError, AgentError) as e:` block, add the increment right before `await self._log_retry(label)`:

```python
            self._retry_count += 1
            await self._log_retry(label)
```

In `_call`, after the retryer completes, add the transient-retry tally. Change:

```python
        try:
            msg = cast(anthropic.types.Message, await retryer(_once))
        except Exception:
            _record_failure(type(self).__name__.lower())
            raise
        _record_success()
        return msg.content[0].text  # type: ignore[union-attr]
```

to:

```python
        try:
            msg = cast(anthropic.types.Message, await retryer(_once))
        except Exception:
            self._retry_count += max(0, retryer.statistics.get("attempt_number", 1) - 1)
            _record_failure(type(self).__name__.lower())
            raise
        self._retry_count += max(0, retryer.statistics.get("attempt_number", 1) - 1)
        _record_success()
        return msg.content[0].text  # type: ignore[union-attr]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agents/test_base_retry_count.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the agent suite to confirm no regression**

Run: `pytest tests/test_agents/ -q`
Expected: PASS (all existing agent tests still green)

- [ ] **Step 6: Commit**

```bash
git add backend/agents/base.py tests/test_agents/test_base_retry_count.py
git commit -m "feat(agents): track BaseAgent.retry_count for Sentry context"
```

---

### Task 5: Capture at the four orchestrator except sites

**Files:**
- Modify: `backend/services/orchestrator.py` (4 `except` sites)
- Test: `tests/test_orchestrator/test_sentry_capture.py`

**Interfaces:**
- Consumes: `capture_pipeline_error(...)` (Task 3); `agent.retry_count` (Task 4).
- Produces: nothing new; the four handled failure paths now also call `capture_pipeline_error`. SSE emission and `upsert_job_result` are unchanged.

The four sites (source `user_id`/`retry_count` from what is in local scope):

| Site | Function | `phase` | `user_id` | `retry_count` |
|------|----------|---------|-----------|---------------|
| 1 (~256) | `_run_phase1` (non-streaming, discovery) | `"phase1"` | `None` (unowned discovery path) | `agent.retry_count` |
| 2 (~390) | `run_evaluate_pipeline` (streaming) | `"phase1"` | `user_id` (local param) | `agent.retry_count` |
| 3 (~512) | `run_steps` sequential | `"phase2"` | `analysis.user_id` | `agent.retry_count` |
| 4 (~566) | `run_steps` parallel `gather` | `"phase2"` | `uid` (local) | `0` (agent out of scope) |

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator/test_sentry_capture.py`:

```python
from unittest.mock import patch

import pytest

from backend.agents.job_parser import AgentError
from backend.services import orchestrator


@pytest.mark.asyncio
async def test_streaming_phase1_failure_captured(db_session, monkeypatch):
    """A failing phase-1 agent in the streaming path calls capture_pipeline_error
    with the agent name + code, and still emits the pipeline_error SSE event."""
    # Force job_parser to raise inside run().
    async def boom(self, *a, **k):
        raise AgentError("bad output")

    monkeypatch.setattr("backend.agents.job_parser.JobParserAgent.run", boom, raising=True)

    captured: list[dict] = []

    def _cap(exc, **kwargs):
        captured.append(kwargs)

    events = []
    with patch.object(orchestrator, "capture_pipeline_error", _cap):
        async for ev in orchestrator.run_evaluate_pipeline(
            "some jd text", db_session, user_id="u1"
        ):
            events.append(ev)

    assert any(k["agent"] == "job_parser" and k["phase"] == "phase1" for k in captured)
    assert any(e.event == "pipeline_error" for e in events)
```

Note for the implementer: confirm the profile fixture exists so
`run_evaluate_pipeline` reaches the agent loop (reuse whatever profile setup the
sibling `tests/test_orchestrator/` tests use; if a profile must be seeded first,
seed it the same way). If the streaming entry proves impractical to drive in a
unit test, target `_run_phase1` directly with a seeded profile instead — the
assertion (capture called with `agent`/`phase`) is what matters.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator/test_sentry_capture.py -q`
Expected: FAIL — `AttributeError: module 'backend.services.orchestrator' has no attribute 'capture_pipeline_error'`

- [ ] **Step 3: Add the import**

In `backend/services/orchestrator.py`, near the other service imports (beside `from backend.services.pipeline_errors import to_user_error`), add:

```python
from backend.services.sentry import capture_pipeline_error
```

- [ ] **Step 4: Wire site 1 — `_run_phase1` (~256)**

In the `except Exception as e:` block that logs `"phase1 agent %s failed"` inside `_run_phase1`, after `ue = to_user_error(agent_name, e)`:

```python
                capture_pipeline_error(
                    e, agent=agent_name, phase="phase1",
                    user_id=None, retry_count=agent.retry_count, error_code=ue.code,
                )
```

- [ ] **Step 5: Wire site 2 — `run_evaluate_pipeline` streaming (~390)**

In the streaming `except Exception as e:` block (the one that also `yield`s the `pipeline_error` SSE event), after `ue = to_user_error(agent_name, e)`:

```python
                capture_pipeline_error(
                    e, agent=agent_name, phase="phase1",
                    user_id=user_id, retry_count=agent.retry_count, error_code=ue.code,
                )
```

- [ ] **Step 6: Wire site 3 — `run_steps` sequential (~512)**

In the sequential `except Exception as e:` block (`logger.exception("step %s failed", name)`), after `ue = to_user_error(name, e)`:

```python
            capture_pipeline_error(
                e, agent=name, phase="phase2",
                user_id=analysis.user_id, retry_count=agent.retry_count, error_code=ue.code,
            )
```

- [ ] **Step 7: Wire site 4 — `run_steps` parallel gather (~566)**

In the parallel-results loop, inside `if isinstance(result, BaseException):` after `ue = to_user_error(name, exc)` (agent is out of scope here — pass `retry_count=0`):

```python
                capture_pipeline_error(
                    exc, agent=name, phase="phase2",
                    user_id=uid, retry_count=0, error_code=ue.code,
                )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_orchestrator/test_sentry_capture.py -q`
Expected: PASS (1 passed)

- [ ] **Step 9: Run the orchestrator suite to confirm no regression**

Run: `pytest tests/test_orchestrator/ -q`
Expected: PASS (all existing orchestrator tests still green)

- [ ] **Step 10: Commit**

```bash
git add backend/services/orchestrator.py tests/test_orchestrator/test_sentry_capture.py
git commit -m "feat(sentry): capture raw pipeline exceptions at the four except sites"
```

---

### Task 6: Init wiring — API lifespan + Celery signals

**Files:**
- Modify: `backend/main.py` (lifespan)
- Modify: `backend/celery_app.py` (signal handlers)
- Test: `tests/test_infra/test_sentry_wiring.py`

**Interfaces:**
- Consumes: `init_sentry(component)` (Task 3).
- Produces: nothing new; Sentry is initialised at API boot and per Celery worker/beat process.

- [ ] **Step 1: Write the failing test**

Create `tests/test_infra/test_sentry_wiring.py`:

```python
from unittest.mock import patch

from celery.signals import beat_init, worker_process_init


def test_worker_process_init_calls_init_sentry():
    import backend.celery_app  # noqa: F401 — ensures handlers are connected

    with patch("backend.services.sentry.init_sentry") as m:
        worker_process_init.send(sender=None)
    m.assert_any_call("worker")


def test_beat_init_calls_init_sentry():
    import backend.celery_app  # noqa: F401

    with patch("backend.services.sentry.init_sentry") as m:
        beat_init.send(sender=None)
    m.assert_any_call("beat")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_infra/test_sentry_wiring.py -q`
Expected: FAIL — the assertion fails because no handler calls `init_sentry` yet.

- [ ] **Step 3: Wire Celery signals**

In `backend/celery_app.py`, add after the imports:

```python
from celery.signals import beat_init, worker_process_init


@worker_process_init.connect
def _init_sentry_worker(**_kwargs: object) -> None:
    # Fires INSIDE each forked child, so the Sentry transport thread is created
    # post-fork (fork-safe). Never init at module import — that is pre-fork.
    from backend.services.sentry import init_sentry

    init_sentry("worker")


@beat_init.connect
def _init_sentry_beat(**_kwargs: object) -> None:
    from backend.services.sentry import init_sentry

    init_sentry("beat")
```

- [ ] **Step 4: Wire the API lifespan**

In `backend/main.py` `lifespan`, make `init_sentry("api")` the first line (before `configure_logging()`):

```python
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from backend.services.sentry import init_sentry

    init_sentry("api")
    configure_logging()
    _check_jwt_secret()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_infra/test_sentry_wiring.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/celery_app.py tests/test_infra/test_sentry_wiring.py
git commit -m "feat(sentry): fork-safe init via lifespan + worker_process_init/beat_init"
```

---

### Task 7: Thread `SENTRY_DSN` through secrets + docs

**Files:**
- Modify: `infra/aws/task-definitions/api.json`
- Modify: `infra/aws/task-definitions/worker.json`
- Modify: `infra/aws/task-definitions/beat.json`
- Modify: `.env.example`
- Modify: `infra/aws/README.md`

**Interfaces:**
- Consumes: `settings.sentry_dsn` reads env `SENTRY_DSN` (Task 1).
- Produces: ECS injects `SENTRY_DSN` from SSM into api/worker/beat containers.

- [ ] **Step 1: Add the secret to each task definition**

In each of `api.json`, `worker.json`, `beat.json`, append to the `secrets` array (after the `OPENAI_API_KEY` entry — add a comma to that line):

```json
        { "name": "SENTRY_DSN", "valueFrom": "arn:aws:ssm:eu-west-2:896476315730:parameter/jobfit/staging/sentry-dsn" }
```

- [ ] **Step 2: Verify each task definition is still valid JSON**

Run: `python -c "import json; [json.load(open(f'infra/aws/task-definitions/{n}.json')) for n in ('api','worker','beat')]; print('valid')"`
Expected: `valid`

- [ ] **Step 3: Add the placeholder to `.env.example`**

Append to `.env.example`:

```
# Sentry error alerting (leave empty to disable). Prod value lives in SSM, not here.
SENTRY_DSN=
```

- [ ] **Step 4: Document the secret in the infra README**

In `infra/aws/README.md`, in the SSM-backed secrets list (where `DATABASE_URL` is listed under the "Sensitive values ... secrets" section), add:

```
- `SENTRY_DSN`
```

And add its parameter path to the SSM parameter list near
`.../parameter/jobfit/staging/database-url`:

```
- `arn:aws:ssm:eu-west-2:<AWS_ACCOUNT_ID>:parameter/jobfit/staging/sentry-dsn`
```

- [ ] **Step 5: Commit**

```bash
git add infra/aws/task-definitions/api.json infra/aws/task-definitions/worker.json infra/aws/task-definitions/beat.json .env.example infra/aws/README.md
git commit -m "chore(infra): thread SENTRY_DSN through SSM + task-def secrets"
```

---

## Final verification (after all tasks)

- [ ] **Run the full suite**

Run: `make check`
Expected: fmt clean, lint clean (ruff + mypy + schema-drift), all tests pass, coverage ≥ 70%.

- [ ] **Update HANDOFF.md** with: Sentry alerting merged; next action = put DSN in SSM `/jobfit/staging/sentry-dsn`, register api/worker/beat task-defs, deploy `v1.3.2`, then smoke-test by forcing one agent failure and confirming a tagged, PII-free event in the `Jobfit-api` Sentry project.

## Notes for the executor

- **Deviation from spec wording:** the spec named "three except sites"; this plan covers **four** — the phase-2 parallel `asyncio.gather` path is also a handled `pipeline_error` emit (where `cover_letter`/`resume_tailorer` run). Covering it is strictly more complete and matches the spec's stated goal ("handled pipeline failures"). Site 4 sources `user_id=uid` and `retry_count=0` because the agent instance is out of scope there.
- **DSN value for SSM**: stored only in SSM at `/jobfit/staging/sentry-dsn` — never committed to this repo. Retrieve it from AWS when registering the parameter.
- If `retryer.statistics` is empty in some tenacity version (no retries occurred), `.get("attempt_number", 1)` yields 1 → increment 0. Safe.
