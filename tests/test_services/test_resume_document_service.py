import json

import pytest
from sqlalchemy import select, update

from backend.models import Profile, ResumeDocument, ResumeDocumentRevision
from backend.schemas import ResumeTailorerOutput
from backend.services import resume_document as svc
from tests.factories import make_user


async def _master(db, user_id) -> ResumeDocument:
    profile = Profile(user_id=user_id, yaml_data="x", merged_profile="m", profile_review_data="{}")
    db.add(profile)
    await db.flush()
    return await svc.get_or_seed_master(db, user_id, profile)


async def test_seed_creates_single_active_default(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    assert doc.name == "Default" and doc.is_active is True and doc.rev == 0
    # calling again returns the same row, not a second one
    versions = await svc.list_master_versions(db_session, user.id)
    assert len(versions) == 1


async def test_apply_write_bumps_rev_and_snapshots(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    updated = await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="New"), base_rev=0, source="inline"
    )
    assert updated.rev == 1
    assert json.loads(updated.content_json)["headline"] == "New"


async def test_stale_base_rev_raises_and_does_not_clobber(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="A"), base_rev=0, source="inline"
    )
    with pytest.raises(svc.StaleRevError):
        await svc.apply_write(
            db_session, doc, ResumeTailorerOutput(headline="B"), base_rev=0, source="chat"
        )
    assert json.loads(doc.content_json)["headline"] == "A"  # unchanged


async def test_set_active_is_exclusive(db_session):
    user = await make_user(db_session)
    await _master(db_session, user.id)
    v2 = await svc.create_version(db_session, user.id, "Aggressive", clone_from=None)
    switched = await svc.set_active(db_session, user.id, v2.id)
    assert switched.is_active is True
    actives = [v for v in await svc.list_master_versions(db_session, user.id) if v.is_active]
    assert len(actives) == 1 and actives[0].id == v2.id


async def test_undo_restores_prior_content(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="V1"), base_rev=0, source="inline"
    )
    undone = await svc.undo(db_session, doc, base_rev=1)
    assert json.loads(undone.content_json)["headline"] == ""  # back to seed content
    assert undone.rev == 2  # non-destructive: undo is a new rev


async def test_apply_write_is_db_level_cas(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    # Simulate a concurrent writer advancing rev out-of-band.
    await db_session.execute(
        update(ResumeDocument).where(ResumeDocument.id == doc.id).values(rev=1)
    )
    await db_session.commit()
    with pytest.raises(svc.StaleRevError):
        await svc.apply_write(
            db_session, doc, ResumeTailorerOutput(headline="X"), base_rev=0, source="chat"
        )


async def test_restore_revision_enables_redo(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="V1"), base_rev=0, source="inline"
    )
    await svc.undo(db_session, doc, base_rev=1)  # doc back to seed content, rev 2
    redone = await svc.restore_revision(
        db_session, doc, base_rev=2, target_rev=1
    )  # frontend redo cursor
    assert json.loads(redone.content_json)["headline"] == "V1"
    assert redone.rev == 3


async def test_apply_write_defaults_doc_kind_to_resume(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="New"), base_rev=0, source="inline"
    )
    snap = (
        await db_session.execute(
            select(ResumeDocumentRevision).where(ResumeDocumentRevision.document_id == doc.id)
        )
    ).scalar_one()
    assert snap.doc_kind == "resume"


async def test_apply_write_accepts_explicit_doc_kind(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session,
        doc,
        ResumeTailorerOutput(headline="New"),
        base_rev=0,
        source="inline",
        doc_kind="cover_letter",
    )
    snap = (
        await db_session.execute(
            select(ResumeDocumentRevision).where(ResumeDocumentRevision.document_id == doc.id)
        )
    ).scalar_one()
    assert snap.doc_kind == "cover_letter"


async def test_delete_version_purges_revisions(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="A"), base_rev=0, source="inline"
    )
    await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="B"), base_rev=1, source="inline"
    )
    existing = (
        (
            await db_session.execute(
                select(ResumeDocumentRevision).where(ResumeDocumentRevision.document_id == doc.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(existing) == 2  # sanity: snapshots exist before delete

    await svc.delete_version(db_session, user.id, doc)

    remaining = (
        (
            await db_session.execute(
                select(ResumeDocumentRevision).where(ResumeDocumentRevision.document_id == doc.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []
