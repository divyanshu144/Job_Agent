from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.cold_email_agent import ColdEmailAgent
from backend.database import get_db
from backend.models import Analysis, Contact, Profile, User
from backend.schemas import ContactRead, DiscoverRequest, DraftResponse, SendResponse
from backend.services.auth_service import get_current_user
from backend.services.contact_discovery import ContactDiscoveryUnavailable, discover_contacts

router = APIRouter(tags=["contacts"])


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    analysis_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRead]:
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (analysis.user_id is not None and analysis.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = await db.execute(
        select(Contact)
        .where(Contact.analysis_id == analysis_id)
        .order_by(Contact.confidence.desc(), Contact.created_at.asc())
    )
    return [ContactRead.model_validate(c) for c in result.scalars()]


@router.post("/contacts/discover", response_model=list[ContactRead])
async def discover(
    body: DiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRead]:
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == body.analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (analysis.user_id is not None and analysis.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Analysis not found")
    try:
        contacts = await discover_contacts(body.analysis_id, db, body.domain)
    except ContactDiscoveryUnavailable as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "contact_discovery_unavailable", "retry": True},
        ) from e
    except ValueError as e:
        if "domain_required" in str(e):
            raise HTTPException(status_code=422, detail={"error": "domain_required"})
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [ContactRead.model_validate(c) for c in contacts]


@router.post("/contacts/{contact_id}/draft", response_model=DraftResponse)
async def draft_email(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftResponse:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == contact.analysis_id))
    ).scalar_one()
    if analysis.user_id is not None and analysis.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    profile = (
        await db.execute(select(Profile).where(Profile.id == analysis.profile_id))
    ).scalar_one()

    agent = ColdEmailAgent().with_tracking(db, analysis_id=analysis.id)
    try:
        result = await agent.run(
            profile=profile.merged_profile,
            jd=analysis.jd_text,
            contact_name=contact.name,
            contact_title=contact.title,
        )
        contact.draft_subject = result.subject
        contact.draft_text = result.body
        contact.status = "drafted"
        await db.commit()
        return DraftResponse(subject=result.subject, body=result.body)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "draft_generation_failed"},
        ) from e


@router.post("/contacts/{contact_id}/send", response_model=SendResponse)
async def send_email(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendResponse:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == contact.analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (analysis.user_id is not None and analysis.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    if contact.status == "sent":
        return SendResponse(sent=True)

    if contact.draft_text is None:
        raise HTTPException(status_code=400, detail={"error": "draft_required"})

    # STUB: Gmail MCP integration not yet wired.
    # To wire: call mcp__claude_ai_Gmail__create_draft then send; update status on success.
    raise HTTPException(
        status_code=503,
        detail={"error": "gmail_unavailable", "retry": True},
    )
