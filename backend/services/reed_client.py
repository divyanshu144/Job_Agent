from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

REED_API = "https://www.reed.co.uk/api/1.0/search"
_MIN_TEXT_LEN = 100
_MAX_RESULTS = 200
_PER_PAGE = 100


async def fetch_reed_jobs(keywords: str, location: str) -> list[RawJob]:
    """Fetch up to 200 jobs from Reed.co.uk using the developer REST API.

    Returns [] immediately if ``settings.reed_api_key`` is empty so the
    discovery pipeline degrades gracefully when the key is not configured.
    """
    if not settings.reed_api_key:
        logger.warning("reed_api_key not configured; skipping Reed fetch")
        return []

    jobs: list[RawJob] = []
    auth = (settings.reed_api_key, "")  # Reed: API key as HTTP Basic username

    async with httpx.AsyncClient(timeout=30, auth=auth) as client:
        for skip in range(0, _MAX_RESULTS, _PER_PAGE):
            params: dict[str, Any] = {
                "keywords": keywords,
                "resultsToTake": _PER_PAGE,
                "resultsToSkip": skip,
            }
            if location:
                params["locationName"] = location
            try:
                resp = await client.get(REED_API, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Reed API error (skip=%d): %s", skip, exc)
                break

            results: list[dict[str, Any]] = resp.json().get("results", [])
            if not results:
                break

            for r in results:
                job_id = str(r.get("jobId", ""))
                if not job_id:
                    continue
                title = r.get("jobTitle", "")
                employer = r.get("employerName", "")
                loc = r.get("locationName", "")
                description = r.get("jobDescription", "")
                url = r.get("jobUrl", f"https://www.reed.co.uk/jobs/{job_id}")
                raw_text = f"{title} at {employer} ({loc})\n\n{description}".strip()
                if len(raw_text) < _MIN_TEXT_LEN:
                    continue
                jobs.append(
                    RawJob(
                        source_id=f"reed_{job_id}",
                        source_url=url,
                        raw_text=raw_text,
                        dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
                    )
                )

    return jobs
