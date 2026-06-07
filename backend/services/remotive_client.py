from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from backend.services.hn_client import RawJob, _strip_html

logger = logging.getLogger(__name__)

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
_CATEGORY = "software-dev"
_LIMIT = 50
_MIN_TEXT_LEN = 100


async def fetch_remotive_jobs() -> list[RawJob]:
    """Fetch software-dev jobs from Remotive's free public API (no auth).

    Returns [] on any HTTP error so the discovery pipeline degrades gracefully.
    """
    jobs: list[RawJob] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(REMOTIVE_API, params={"category": _CATEGORY, "limit": _LIMIT})
            resp.raise_for_status()
            results: list[dict[str, Any]] = resp.json().get("jobs", [])
    except httpx.HTTPError as exc:
        logger.warning("Remotive API error: %s", exc)
        return []

    for r in results:
        job_id = str(r.get("id", ""))
        if not job_id:
            continue
        title = r.get("title", "")
        company = r.get("company_name", "")
        location = r.get("candidate_required_location", "")
        description = _strip_html(r.get("description", ""))
        url = r.get("url", "")
        raw_text = f"{title} at {company} ({location})\n\n{description}".strip()
        if len(raw_text) < _MIN_TEXT_LEN:
            continue
        jobs.append(
            RawJob(
                source_id=f"remotive_{job_id}",
                source_url=url,
                raw_text=raw_text,
                dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
            )
        )
    return jobs
