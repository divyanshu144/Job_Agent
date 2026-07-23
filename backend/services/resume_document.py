from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Profile, ResumeDocument, ResumeDocumentRevision
from backend.schemas import ResumeTailorerOutput
from backend.services.resume_errors import StaleRevError
from backend.services.resume_seed import seed_resume_content

REVISION_LIMIT = 50


async def _prune(db: AsyncSession, document_id: str) -> None:
    """Keep only the newest REVISION_LIMIT snapshots (by rev desc) for a document."""
    rows = (
        (
            await db.execute(
                select(ResumeDocumentRevision)
                .where(ResumeDocumentRevision.document_id == document_id)
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
    # restore_revision's scalar_one_or_none() raise MultipleResultsFound.
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
    await db.execute(
        delete(ResumeDocumentRevision).where(ResumeDocumentRevision.document_id == doc.id)
    )
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
    doc_kind: str = "resume",
) -> ResumeDocument:
    # Capture the PK before any rollback: rollback() unconditionally expires ORM
    # instances, so reading doc.id afterwards would trigger a sync lazy-load (illegal
    # in async). The post-rollback select() below re-populates this same doc instance.
    document_id = doc.id
    # Snapshot the pre-write state at base_rev. If the CAS below loses, the rollback
    # discards this insert, so no orphan/duplicate snapshot is persisted.
    db.add(
        ResumeDocumentRevision(
            document_id=document_id,
            doc_kind=doc_kind,
            rev=base_rev,
            content_json=doc.content_json,
            source=source,
            summary=summary,
        )
    )
    # Suppress autoflush so the pending snapshot insert is not flushed until the CAS
    # decision. On the losing path the rollback discards it (avoiding a duplicate
    # (document_id, rev) row that the unique constraint would otherwise reject before
    # we can raise StaleRevError); on the winning path it flushes within the commit.
    with db.no_autoflush:
        result = await db.execute(
            update(ResumeDocument)
            .where(ResumeDocument.id == document_id, ResumeDocument.rev == base_rev)
            .values(content_json=new_content.model_dump_json(), rev=base_rev + 1)
        )
    if result.rowcount == 0:
        await db.rollback()
        current = (
            await db.execute(select(ResumeDocument).where(ResumeDocument.id == document_id))
        ).scalar_one()
        raise StaleRevError(current=current)
    await _prune(db, document_id)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_revisions(db: AsyncSession, doc: ResumeDocument) -> list[ResumeDocumentRevision]:
    return list(
        (
            await db.execute(
                select(ResumeDocumentRevision)
                .where(ResumeDocumentRevision.document_id == doc.id)
                .order_by(ResumeDocumentRevision.rev)
            )
        )
        .scalars()
        .all()
    )


async def restore_revision(
    db: AsyncSession, doc: ResumeDocument, base_rev: int, target_rev: int
) -> ResumeDocument:
    snap = (
        await db.execute(
            select(ResumeDocumentRevision).where(
                ResumeDocumentRevision.document_id == doc.id,
                ResumeDocumentRevision.rev == target_rev,
            )
        )
    ).scalar_one_or_none()
    if snap is None:
        return doc  # nothing to restore at that rev
    content = ResumeTailorerOutput.model_validate_json(snap.content_json)
    return await apply_write(db, doc, content, base_rev=base_rev, source="undo")


async def undo(db: AsyncSession, doc: ResumeDocument, base_rev: int) -> ResumeDocument:
    return await restore_revision(db, doc, base_rev, target_rev=base_rev - 1)


async def get_active_master(db: AsyncSession, user_id: str) -> ResumeDocument | None:
    return (
        await db.execute(
            select(ResumeDocument).where(
                ResumeDocument.user_id == user_id,
                ResumeDocument.kind == "master",
                ResumeDocument.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def get_analysis_resume(
    db: AsyncSession, user_id: str, analysis_id: str
) -> ResumeDocument | None:
    return (
        await db.execute(
            select(ResumeDocument).where(
                ResumeDocument.user_id == user_id,
                ResumeDocument.analysis_id == analysis_id,
                ResumeDocument.kind == "analysis",
                ResumeDocument.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def ensure_analysis_resume(
    db: AsyncSession, user_id: str, analysis_id: str, content_json: str
) -> ResumeDocument | None:
    """Create the per-analysis editable fork — ONLY if the analysis has none yet.
    A pipeline retry must never clobber a fork the user may have edited."""
    existing = await get_analysis_resume(db, user_id, analysis_id)
    if existing is not None:
        return existing
    doc = ResumeDocument(
        user_id=user_id,
        analysis_id=analysis_id,
        kind="analysis",
        name="Tailored",
        content_json=content_json,
        is_active=True,
        rev=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def promote_analysis_to_master(
    db: AsyncSession, user_id: str, fork: ResumeDocument, name: str
) -> ResumeDocument:
    """Non-destructive §3.1 'Save to master': a NEW active master version carries the
    fork's content; the previous master survives as an inactive version."""
    promoted = ResumeDocument(
        user_id=user_id,
        kind="master",
        name=name,
        content_json=fork.content_json,
        is_active=False,
        rev=0,
    )
    db.add(promoted)
    await db.flush()
    return await set_active(db, user_id, promoted.id)
