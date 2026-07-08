"""Sentry error alerting: init + pipeline-error capture, PII-scrubbed.

Disabled when settings.sentry_dsn is empty (local dev + tests never emit).
Capture happens at the orchestrator except sites with the RAW exception; the
user-facing pipeline_error SSE event stays sanitized. Never raises (fail-open):
a monitoring failure must not break app boot or turn a handled agent error into
an unhandled one.
"""

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
