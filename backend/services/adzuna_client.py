from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

ADZUNA_API = "https://api.adzuna.com/v1/api/jobs"
_MIN_TEXT_LEN = 100
_PER_PAGE = 50
_MAX_PAGES = 4   # up to 200 results per run
_COUNTRY = "gb"  # UK endpoint


async def fetch_adzuna_jobs(keywords: str, location: str) -> list[RawJob]:
    """Fetch up to 200 jobs from Adzuna (UK) using the public REST API.

    Returns [] immediately if either ``adzuna_app_id`` or ``adzuna_app_key``
    is empty so the pipeline degrades gracefully when credentials are absent.
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        logger.warning("adzuna credentials not configured; skipping Adzuna fetch")
        return []

    jobs: list[RawJob] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, _MAX_PAGES + 1):
            params: dict[str, Any] = {
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_app_key,
                "results_per_page": _PER_PAGE,
                "content-type": "application/json",
            }
            if keywords:
                params["what"] = keywords
            if location:
                params["where"] = location

            try:
                resp = await client.get(
                    f"{ADZUNA_API}/{_COUNTRY}/search/{page}", params=params
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Adzuna API error (page=%d): %s", page, exc)
                break

            results: list[dict[str, Any]] = resp.json().get("results", [])
            if not results:
                break

            for r in results:
                job_id = str(r.get("id", ""))
                if not job_id:
                    continue
                title = r.get("title", "")
                company_info: dict[str, Any] = r.get("company") or {}
                loc_info: dict[str, Any] = r.get("location") or {}
                company = company_info.get("display_name", "")
                loc = loc_info.get("display_name", "")
                description = r.get("description", "")
                url = r.get(
                    "redirect_url",
                    f"https://www.adzuna.co.uk/jobs/details/{job_id}",
                )
                raw_text = f"{title} at {company} ({loc})\n\n{description}".strip()
                if len(raw_text) < _MIN_TEXT_LEN:
                    continue
                jobs.append(
                    RawJob(
                        source_id=f"adzuna_{job_id}",
                        source_url=url,
                        raw_text=raw_text,
                        dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
                    )
                )

    return jobs
