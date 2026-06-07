from __future__ import annotations

import hashlib
import html
import logging
from typing import Any

import httpx

from backend.services.hn_client import RawJob, _strip_html

logger = logging.getLogger(__name__)

_MIN_TEXT_LEN = 100

# Public board/posting endpoints per ATS. {slug} is substituted at call time.
# Greenhouse: the legacy boards.greenhouse.io/{slug}/jobs.json host 404s; the
# current Job Board API is boards-api.greenhouse.io/v1/boards/{slug}/jobs.
_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def detect_ats(jobs_url: str) -> str | None:
    """Identify the ATS provider from a company's jobs_url by host substring."""
    if not jobs_url:
        return None
    url = jobs_url.lower()
    if "greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "ashbyhq" in url:
        return "ashby"
    return None


def _extract_slug(jobs_url: str) -> str | None:
    """Pull the board slug (first non-empty path segment) from a jobs_url."""
    if not jobs_url:
        return None
    # Strip scheme + host, keep the path
    path = jobs_url.split("//", 1)[-1]
    parts = [p for p in path.split("/")[1:] if p]
    return parts[0] if parts else None


def _make_raw_job(ats: str, slug: str, job_id: str, url: str, raw_text: str) -> RawJob | None:
    raw_text = raw_text.strip()
    if not job_id or len(raw_text) < _MIN_TEXT_LEN:
        return None
    return RawJob(
        source_id=f"{ats}_{slug}_{job_id}",
        source_url=url,
        raw_text=raw_text,
        dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
    )


def _normalise_greenhouse(slug: str, data: Any) -> list[RawJob]:
    jobs: list[RawJob] = []
    for r in data.get("jobs", []):
        location = (r.get("location") or {}).get("name", "")
        # Greenhouse returns `content` as HTML-escaped markup (e.g. &lt;p&gt;), so
        # unescape before stripping tags — otherwise tags survive into raw_text.
        content = _strip_html(html.unescape(r.get("content", "")))
        raw_text = f"{r.get('title', '')} ({location})\n\n{content}"
        job = _make_raw_job(
            "greenhouse", slug, str(r.get("id", "")), r.get("absolute_url", ""), raw_text
        )
        if job:
            jobs.append(job)
    return jobs


def _normalise_lever(slug: str, data: Any) -> list[RawJob]:
    jobs: list[RawJob] = []
    for r in data:
        location = (r.get("categories") or {}).get("location", "")
        desc = r.get("descriptionPlain") or _strip_html(r.get("description", ""))
        raw_text = f"{r.get('text', '')} ({location})\n\n{desc}"
        job = _make_raw_job("lever", slug, str(r.get("id", "")), r.get("hostedUrl", ""), raw_text)
        if job:
            jobs.append(job)
    return jobs


def _normalise_ashby(slug: str, data: Any) -> list[RawJob]:
    jobs: list[RawJob] = []
    for r in data.get("jobs", []):
        desc = r.get("descriptionPlain") or _strip_html(r.get("description", ""))
        raw_text = f"{r.get('title', '')} ({r.get('location', '')})\n\n{desc}"
        job = _make_raw_job("ashby", slug, str(r.get("id", "")), r.get("jobUrl", ""), raw_text)
        if job:
            jobs.append(job)
    return jobs


_NORMALISERS = {
    "greenhouse": _normalise_greenhouse,
    "lever": _normalise_lever,
    "ashby": _normalise_ashby,
}


async def fetch_ats_jobs(ats: str, slug: str) -> list[RawJob]:
    """Query one ATS board and normalise to RawJob. Returns [] on HTTP error
    or unknown ATS so a single bad board never aborts a discovery run."""
    endpoint = _ENDPOINTS.get(ats)
    normaliser = _NORMALISERS.get(ats)
    if endpoint is None or normaliser is None:
        logger.warning("Unknown ATS %r for slug %r", ats, slug)
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(endpoint.format(slug=slug))
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("ATS %s fetch error for %s: %s", ats, slug, exc)
        return []
    return normaliser(slug, data)
