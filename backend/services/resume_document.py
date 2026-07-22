from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Profile, ResumeDocument, ResumeDocumentRevision
from backend.schemas import ResumeTailorerOutput
from backend.services.resume_errors import StaleRevError
from backend.services.resume_seed import seed_resume_content

REVISION_LIMIT = 50


async def _snapshot(
    db: AsyncSession, doc: ResumeDocument, source: str, summary: str | None
) -> None:
    db.add(
        ResumeDocumentRevision(
            document_id=doc.id,
            doc_kind="resume",
            rev=doc.rev,
            content_json=doc.content_json,
            source=source,
            summary=summary,
        )
    )
    rows = (
        (
            await db.execute(
                select(ResumeDocumentRevision)
                .where(ResumeDocumentRevision.document_id == doc.id)
                .order_by(ResumeDocumentRevision.rev.desc())
            )
        )
        .scalars()
        .all()
    )
    for stale in rows[REVISION_LIMIT:]:
        await db.delete(stale)


async def list_master_versions(db: AsyncSession, user_id: str) -> list[ResumeDocument]:
    return list(
        (
            await db.execute(
                select(ResumeDocument)
                .where(ResumeDocument.user_id == user_id, ResumeDocument.kind == "master")
                .order_by(ResumeDocument.created_at)
            )
        )
        .scalars()
        .all()
    )


async def get_or_seed_master(db: AsyncSession, user_id: str, profile: Profile) -> ResumeDocument:
    existing = await list_master_versions(db, user_id)
    if existing:
        active = next((d for d in existing if d.is_active), existing[0])
        return active
    content = seed_resume_content(profile)
    doc = ResumeDocument(
        user_id=user_id,
        kind="master",
        name="Default",
        content_json=content.model_dump_json(),
        is_active=True,
        rev=0,
    )
    db.add(doc)
    await db.flush()
    # No revision snapshot here: apply_write() snapshots the pre-write state on the
    # first real write, which captures this seed content at rev 0. An extra snapshot
    # here would collide with that one (same document_id + rev=0) and make
    # _neighbour_content's scalar_one_or_none() raise MultipleResultsFound.
    await db.commit()
    await db.refresh(doc)
    return doc


async def create_version(
    db: AsyncSession, user_id: str, name: str, clone_from: ResumeDocument | None
) -> ResumeDocument:
    content_json = clone_from.content_json if clone_from is not None else "{}"
    doc = ResumeDocument(
        user_id=user_id, kind="master", name=name, content_json=content_json, is_active=False, rev=0
    )
    db.add(doc)
    await db.flush()
    # Same reasoning as get_or_seed_master: no snapshot here, apply_write() covers it.
    await db.commit()
    await db.refresh(doc)
    return doc


async def set_active(db: AsyncSession, user_id: str, doc_id: str) -> ResumeDocument:
    versions = await list_master_versions(db, user_id)
    target = next((d for d in versions if d.id == doc_id), None)
    if target is None:
        raise KeyError(doc_id)
    for d in versions:
        d.is_active = d.id == doc_id
    await db.commit()
    await db.refresh(target)
    return target


async def rename_version(db: AsyncSession, doc: ResumeDocument, name: str) -> ResumeDocument:
    doc.name = name
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_version(db: AsyncSession, user_id: str, doc: ResumeDocument) -> None:
    was_active = doc.is_active
    await db.delete(doc)
    await db.flush()
    if was_active:
        remaining = await list_master_versions(db, user_id)
        if remaining:
            newest = max(remaining, key=lambda d: d.updated_at)
            newest.is_active = True
    await db.commit()


async def apply_write(
    db: AsyncSession,
    doc: ResumeDocument,
    new_content: ResumeTailorerOutput,
    base_rev: int,
    source: str,
    summary: str | None = None,
) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    await _snapshot(db, doc, source=source, summary=summary)  # snapshot the pre-write state
    doc.content_json = new_content.model_dump_json()
    doc.rev = doc.rev + 1
    await db.commit()
    await db.refresh(doc)
    return doc


async def _neighbour_content(db: AsyncSession, doc: ResumeDocument, target_rev: int) -> str | None:
    row = (
        await db.execute(
            select(ResumeDocumentRevision).where(
                ResumeDocumentRevision.document_id == doc.id,
                ResumeDocumentRevision.rev == target_rev,
            )
        )
    ).scalar_one_or_none()
    return row.content_json if row is not None else None


async def undo(db: AsyncSession, doc: ResumeDocument, base_rev: int) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    prior = await _neighbour_content(db, doc, doc.rev - 1)
    if prior is None:
        return doc  # nothing to undo
    content = ResumeTailorerOutput.model_validate_json(prior)
    return await apply_write(db, doc, content, base_rev=doc.rev, source="undo")


async def redo(db: AsyncSession, doc: ResumeDocument, base_rev: int) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    nxt = await _neighbour_content(db, doc, doc.rev + 1)
    if nxt is None:
        return doc
    content = ResumeTailorerOutput.model_validate_json(nxt)
    return await apply_write(db, doc, content, base_rev=doc.rev, source="undo")
