from __future__ import annotations

import backend.models  # noqa: F401
from backend.models import ResumeDocument, ResumeDocumentRevision, ResumeEditRule
from tests.factories import make_user


async def test_resume_document_defaults(db_session):
    user = await make_user(db_session)
    doc = ResumeDocument(user_id=user.id, kind="master", name="Default", content_json="{}")
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    assert doc.id
    assert doc.rev == 0
    assert doc.is_active is False
    assert doc.analysis_id is None


async def test_revision_and_rule_persist(db_session):
    user = await make_user(db_session)
    doc = ResumeDocument(user_id=user.id, kind="master", name="Default", content_json="{}")
    db_session.add(doc)
    await db_session.flush()
    db_session.add(
        ResumeDocumentRevision(
            document_id=doc.id, doc_kind="resume", rev=0, content_json="{}", source="seed"
        )
    )
    db_session.add(ResumeEditRule(user_id=user.id, mode="never", text="utilized", scope="resume"))
    await db_session.commit()
    assert doc.id
