from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from backend.services.hn_client import RawJob, _strip_html

logger = logging.getLogger(__name__)

WORKATASTARTUP_URL = (
    "https://www.workatastartup.com/companies"
    "?demographic=any&hasEquity=any&hasSalary=any&industry=any"
    "&interviewProcess=any&jobType=any&layout=list-compact"
    "&sortBy=created_desc&tab=any&usVisaNotRequired=true"
)
_YC_ROOT = "https://www.ycombinator.com"
_WAAS_ROOT = "https://www.workatastartup.com"
_MIN_TEXT_LEN = 100
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": ("Mozilla/5.0 (compatible; JobReadyAgent/1.0; +https://www.workatastartup.com/)"),
}


@dataclass(frozen=True)
class WorkAtAStartupListing:
    job_id: str
    title: str
    company: str
    location: str
    apply_url: str
    canonical_url: str
    description: str
    role_type: str
    job_type: str
    salary: str
    equity: str
    experience: str
    company_one_liner: str
    company_description: str
    company_batch: str
    company_location: str
    company_website: str
    skills: list[str]
    tags: list[str]
    remote: str
    visa: str


class WorkAtAStartupAdapter:
    def __init__(self, listing_url: str = WORKATASTARTUP_URL) -> None:
        self.listing_url = listing_url

    async def fetch_jobs(self) -> list[RawJob]:
        try:
            async with httpx.AsyncClient(timeout=30, headers=_HEADERS) as client:
                resp = await client.get(self.listing_url)
                resp.raise_for_status()

            listings = parse_workatastartup_listings(resp.text)
            jobs: list[RawJob] = []
            seen: set[str] = set()
            for listing in listings:
                job = _listing_to_raw_job(listing)
                if job is None or job.dedup_hash in seen:
                    continue
                seen.add(job.dedup_hash)
                jobs.append(job)
            return jobs
        except Exception as exc:
            logger.warning("WorkAtAStartup fetch/parse error: %s", exc)
            return []


def _extract_data_pages(text: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for match in re.finditer(r'data-page="([^"]+)"', text):
        try:
            pages.append(json.loads(html.unescape(match.group(1))))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("WorkAtAStartup data-page parse failed: %s", exc)
    return pages


def _as_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _real_url(job: dict[str, Any]) -> str:
    url = _as_str(job.get("url") or job.get("canonicalUrl") or job.get("canonical_url"))
    if url:
        root = _YC_ROOT if url.startswith("/companies/") else _WAAS_ROOT
        return urljoin(root, url)
    return ""


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in (_as_str(v) for v in value) if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _listing_from_job(job: dict[str, Any]) -> WorkAtAStartupListing | None:
    job_id = _as_str(job.get("id"))
    title = _as_str(job.get("title"))
    company = _as_str(job.get("companyName") or job.get("company_name"))
    if not job_id or not title or not company:
        return None
    description = _as_str(job.get("description"))
    real_url = _real_url(job)
    apply_url = _as_str(job.get("applyUrl") or job.get("apply_url"))
    if not apply_url and not real_url:
        return None
    return WorkAtAStartupListing(
        job_id=job_id,
        title=title,
        company=company,
        location=_as_str(job.get("location")),
        apply_url=apply_url,
        canonical_url=real_url,
        description=_strip_html(html.unescape(description)),
        role_type=_as_str(job.get("roleType") or job.get("prettyRole") or job.get("role")),
        job_type=_as_str(job.get("jobType") or job.get("type")),
        salary=_as_str(job.get("salary") or job.get("salaryRange")),
        equity=_as_str(job.get("equity") or job.get("equityRange")),
        experience=_as_str(job.get("experience") or job.get("minExperience")),
        company_one_liner=_as_str(job.get("companyOneLiner") or job.get("company_one_liner")),
        company_description=_strip_html(
            html.unescape(_as_str(job.get("companyDescription") or job.get("company_description")))
        ),
        company_batch=_as_str(job.get("companyBatch") or job.get("companyBatchName")),
        company_location=_as_str(job.get("companyLocation") or job.get("company_location")),
        company_website=_as_str(job.get("companyWebsite") or job.get("company_website")),
        skills=_as_str_list(job.get("skills")),
        tags=_as_str_list(job.get("tags")),
        remote=_as_str(job.get("remote") or job.get("remotePolicy") or job.get("jobLocationType")),
        visa=_as_str(job.get("visa") or job.get("visaSponsorship") or job.get("sponsorship")),
    )


def _iter_jobs(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("job"), dict):
            found.append(value["job"])
        jobs = value.get("jobs")
        if isinstance(jobs, list):
            found.extend(j for j in jobs if isinstance(j, dict))
        for child in value.values():
            found.extend(_iter_jobs(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_iter_jobs(item))
    return found


def parse_workatastartup_listings(text: str) -> list[WorkAtAStartupListing]:
    listings: list[WorkAtAStartupListing] = []
    seen_ids: set[str] = set()
    for page in _extract_data_pages(text):
        for job in _iter_jobs(page.get("props", page)):
            listing = _listing_from_job(job)
            if listing is None or listing.job_id in seen_ids:
                continue
            seen_ids.add(listing.job_id)
            listings.append(listing)
    return listings


def _listing_to_raw_job(listing: WorkAtAStartupListing) -> RawJob | None:
    source_url = listing.apply_url or listing.canonical_url
    if not source_url:
        return None

    description = listing.description or "No public description was available on the listing page."
    details = [
        f"{listing.title} at {listing.company} ({listing.location})",
        f"Company one-liner: {listing.company_one_liner}" if listing.company_one_liner else "",
        f"Company description: {listing.company_description}"
        if listing.company_description
        else "",
        f"Company batch: {listing.company_batch}" if listing.company_batch else "",
        f"Company location: {listing.company_location}" if listing.company_location else "",
        f"Company website: {listing.company_website}" if listing.company_website else "",
        f"Role type: {listing.role_type}" if listing.role_type else "",
        f"Job type: {listing.job_type}" if listing.job_type else "",
        f"Salary: {listing.salary}" if listing.salary else "",
        f"Equity: {listing.equity}" if listing.equity else "",
        f"Experience: {listing.experience}" if listing.experience else "",
        f"Skills: {', '.join(listing.skills)}" if listing.skills else "",
        f"Tags: {', '.join(listing.tags)}" if listing.tags else "",
        f"Remote: {listing.remote}" if listing.remote else "",
        f"Visa/sponsorship: {listing.visa}" if listing.visa else "",
        f"Canonical WorkAtAStartup URL: {listing.canonical_url}" if listing.canonical_url else "",
        f"External apply URL: {listing.apply_url}" if listing.apply_url else "",
        "",
        description,
    ]
    raw_text = "\n".join(part for part in details if part).strip()
    if len(raw_text) < _MIN_TEXT_LEN:
        return None

    dedup_key = listing.canonical_url or f"workatastartup:{listing.job_id}"
    return RawJob(
        source_id=f"workatastartup_{listing.job_id}",
        source_url=source_url,
        raw_text=raw_text,
        dedup_hash=hashlib.sha256(dedup_key.encode()).hexdigest(),
    )


async def fetch_workatastartup_jobs() -> list[RawJob]:
    return await WorkAtAStartupAdapter().fetch_jobs()
