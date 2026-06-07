from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.services.ats_client import _extract_slug, detect_ats, fetch_ats_jobs
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

YC_COMPANIES_API = "https://api.ycombinator.com/v0.1/companies"


async def fetch_yc_jobs() -> list[RawJob]:
    """Fetch YC companies that are hiring, resolve each to its ATS board, and
    aggregate the postings. Returns [] on a top-level HTTP error; individual
    companies that fail (unknown ATS or fetch error) are skipped, not fatal."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(YC_COMPANIES_API, params={"is_hiring": "true"})
            resp.raise_for_status()
            payload: Any = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("YC companies API error: %s", exc)
        return []

    companies = payload.get("companies", []) if isinstance(payload, dict) else payload

    jobs: list[RawJob] = []
    for company in companies:
        jobs_url = company.get("jobs_url", "")
        ats = detect_ats(jobs_url)
        if ats is None:
            continue
        slug = _extract_slug(jobs_url)
        if slug is None:
            continue
        try:
            jobs.extend(await fetch_ats_jobs(ats, slug))
        except Exception as exc:  # one company must never abort the rest
            logger.warning("YC company %s (%s/%s) failed: %s", company.get("name"), ats, slug, exc)
            continue
    return jobs
