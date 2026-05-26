from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Analysis, Contact, JobResult


class ContactDiscoveryUnavailable(Exception):
    pass


TITLE_PRIORITY = ["hiring manager", "engineering manager", "recruiter", "founder"]


def _title_rank(title: str | None) -> int:
    if not title:
        return len(TITLE_PRIORITY)
    t = title.lower()
    for i, keyword in enumerate(TITLE_PRIORITY):
        if keyword in t:
            return i
    return len(TITLE_PRIORITY)


async def discover_contacts(
    analysis_id: str,
    db: AsyncSession,
    domain: str | None = None,
) -> list[Contact]:
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None:
        raise ValueError(f"Analysis {analysis_id} not found")

    jp_row = (
        await db.execute(
            select(JobResult).where(
                JobResult.analysis_id == analysis_id,
                JobResult.agent_name == "job_parser",
            )
        )
    ).scalar_one_or_none()

    company: str | None = None
    if jp_row and jp_row.output_json:
        try:
            company = json.loads(jp_row.output_json).get("company")
        except (json.JSONDecodeError, AttributeError):
            pass

    if domain is None:
        if not company:
            raise ValueError("domain_required")
        domain = company.lower().replace(" ", "") + ".com"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "limit": 10, "api_key": settings.hunter_api_key},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ContactDiscoveryUnavailable(str(e)) from e
        except httpx.RequestError as e:
            raise ContactDiscoveryUnavailable(str(e)) from e

    emails = (resp.json().get("data") or {}).get("emails", [])
    emails = [e for e in emails if e.get("value")]
    emails.sort(key=lambda e: _title_rank(e.get("position")))

    await db.execute(delete(Contact).where(Contact.analysis_id == analysis_id))

    contacts: list[Contact] = []
    for e in emails:
        first = e.get("first_name", "") or ""
        last = e.get("last_name", "") or ""
        full_name = f"{first} {last}".strip() or None
        contact = Contact(
            id=str(uuid4()),
            analysis_id=analysis_id,
            email=e["value"],
            name=full_name,
            title=e.get("position"),
            company=company,
            source="hunter",
            confidence=float(e.get("confidence") or 0) / 100.0,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        )
        db.add(contact)
        contacts.append(contact)

    await db.commit()
    return contacts
