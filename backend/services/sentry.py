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
