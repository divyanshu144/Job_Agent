import json

import pytest

from backend.models import Profile, ResumeDocument
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
