from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import AgentError
from backend.database import get_db
from backend.models import ResumeDocument, ResumeEditRule, User
from backend.schemas import (
    EditRuleCreate,
    EditRuleResponse,
    ResumeChatRequest,
    ResumeContentUpdate,
    ResumeDocumentResponse,
    ResumeRevisionSummary,
    ResumeTailorerOutput,
    ResumeVersionCreate,
    ResumeVersionPatch,
    ResumeVersionSummary,
)
from backend.services import resume_chat
from backend.services import resume_document as svc
from backend.services.auth_service import get_current_user
from backend.services.profile_builder import get_owned_profile
from backend.services.resume_errors import StaleRevError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resume"])


def _to_response(doc: ResumeDocument) -> ResumeDocumentResponse:
    return ResumeDocumentResponse(
        id=doc.id,
        kind=doc.kind,
        name=doc.name,
        is_active=doc.is_active,
        rev=doc.rev,
        content=ResumeTailorerOutput.model_validate(json.loads(doc.content_json or "{}")),
        updated_at=doc.updated_at,
    )


async def _owned_master(db: AsyncSession, doc_id: str, user_id: str) -> ResumeDocument:
    doc = (
        await db.execute(
            select(ResumeDocument).where(
                ResumeDocument.id == doc_id,
                ResumeDocument.user_id == user_id,
                ResumeDocument.kind == "master",
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Resume version not found")
    return doc


@router.get("/resume", response_model=ResumeDocumentResponse)
async def get_active_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    profile = await get_owned_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="Build your profile before creating a resume")
    doc = await svc.get_or_seed_master(db, current_user.id, profile)
    return _to_response(doc)


@router.get("/resume/versions", response_model=list[ResumeVersionSummary])
async def list_versions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResumeVersionSummary]:
    rows = await svc.list_master_versions(db, current_user.id)
    return [
        ResumeVersionSummary(
            id=d.id, name=d.name, is_active=d.is_active, rev=d.rev, updated_at=d.updated_at
        )
        for d in rows
    ]


@router.get("/resume/versions/{doc_id}", response_model=ResumeDocumentResponse)
async def get_version(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    # Recovery path for a 409 on a non-active version (design §5.3): the client can
    # fetch any owned version's current content directly by id, not just the active one.
    doc = await _owned_master(db, doc_id, current_user.id)
    return _to_response(doc)


@router.post("/resume/versions", response_model=ResumeDocumentResponse)
async def create_version(
    data: ResumeVersionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    clone = None
    if data.clone_active:
        versions = await svc.list_master_versions(db, current_user.id)
        clone = next((d for d in versions if d.is_active), None)
    doc = await svc.create_version(db, current_user.id, data.name, clone_from=clone)
    return _to_response(doc)


@router.patch("/resume/versions/{doc_id}", response_model=ResumeDocumentResponse)
async def patch_version(
    doc_id: str,
    data: ResumeVersionPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    if data.name is not None:
        doc = await svc.rename_version(db, doc, data.name)
    if data.make_active:
        doc = await svc.set_active(db, current_user.id, doc_id)
    return _to_response(doc)


@router.delete("/resume/versions/{doc_id}", status_code=204)
async def delete_version(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    doc = await _owned_master(db, doc_id, current_user.id)
    await svc.delete_version(db, current_user.id, doc)
    return Response(status_code=204)


@router.patch("/resume/{doc_id}/content", response_model=ResumeDocumentResponse)
async def patch_content(
    doc_id: str,
    data: ResumeContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.apply_write(db, doc, data.content, base_rev=data.base_rev, source="inline")
    except StaleRevError as exc:
        current = exc.current
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Resume changed; reload and retry",
                "rev": current.rev,
                "content": json.loads(current.content_json or "{}"),
            },
        ) from exc
    return _to_response(doc)


def _sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@router.post("/resume/{doc_id}/chat")
async def chat_edit(
    doc_id: str,
    data: ResumeChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # Auth + ownership resolved BEFORE streaming (real 401/404).
    doc = await _owned_master(db, doc_id, current_user.id)

    async def _stream() -> AsyncGenerator[str, None]:
        yield _sse("edit_start", {"doc_id": doc.id})
        try:
            result = await resume_chat.apply_chat_edit(
                db, doc, current_user.id, base_rev=data.base_rev, instruction=data.instruction
            )
            yield _sse("edit_done", result.model_dump(mode="json"))
        except StaleRevError as exc:
            current = exc.current
            yield _sse(
                "edit_conflict",
                {"rev": current.rev, "content": json.loads(current.content_json or "{}")},
            )
        except AgentError as exc:
            yield _sse(
                "edit_error", {"message": "Could not apply that change — your resume is unchanged."}
            )
            logger.warning("resume chat edit failed for doc %s: %s", doc.id, exc)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/resume/{doc_id}/undo", response_model=ResumeDocumentResponse)
async def undo_content(
    doc_id: str,
    base_rev: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.undo(db, doc, base_rev=base_rev)
    except StaleRevError as exc:
        current = exc.current
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Resume changed; reload and retry",
                "rev": current.rev,
                "content": json.loads(current.content_json or "{}"),
            },
        ) from exc
    return _to_response(doc)


@router.post("/resume/{doc_id}/restore", response_model=ResumeDocumentResponse)
async def restore_content(
    doc_id: str,
    base_rev: int,
    target_rev: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    # Cursor-driven restore: the frontend performs REDO (and jump-to-revision) by passing the
    # target rev. A parameterless server-side redo cannot work against an append-only log.
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.restore_revision(db, doc, base_rev=base_rev, target_rev=target_rev)
    except StaleRevError as exc:
        current = exc.current
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Resume changed; reload and retry",
                "rev": current.rev,
                "content": json.loads(current.content_json or "{}"),
            },
        ) from exc
    return _to_response(doc)


@router.get("/resume/{doc_id}/revisions", response_model=list[ResumeRevisionSummary])
async def list_document_revisions(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResumeRevisionSummary]:
    # The frontend's undo-cursor source of truth (design §3.4).
    doc = await _owned_master(db, doc_id, current_user.id)
    revs = await svc.list_revisions(db, doc)
    return [
        ResumeRevisionSummary(
            rev=r.rev, source=r.source, summary=r.summary, created_at=r.created_at
        )
        for r in revs
    ]


@router.get("/resume/rules", response_model=list[EditRuleResponse])
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EditRuleResponse]:
    rows = (
        (
            await db.execute(
                select(ResumeEditRule)
                .where(ResumeEditRule.user_id == current_user.id)
                .order_by(ResumeEditRule.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [EditRuleResponse(id=r.id, mode=r.mode, text=r.text, scope=r.scope) for r in rows]


@router.post("/resume/rules", response_model=EditRuleResponse)
async def add_rule(
    data: EditRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EditRuleResponse:
    row = ResumeEditRule(user_id=current_user.id, mode=data.mode, text=data.text, scope=data.scope)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return EditRuleResponse(id=row.id, mode=row.mode, text=row.text, scope=row.scope)


@router.delete("/resume/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = (
        await db.execute(
            select(ResumeEditRule).where(
                ResumeEditRule.id == rule_id, ResumeEditRule.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
