from __future__ import annotations

import json

import backend.models  # noqa: F401
from backend.services import resume_document as docsvc
from tests.factories import make_analysis, make_profile

_USER_ID = "test-user-id"


async def _fork(db_session, headline="Tailored for Acme"):
    analysis = await make_analysis(db_session, user_id=_USER_ID)
    doc = await docsvc.ensure_analysis_resume(
        db_session, _USER_ID, analysis.id, json.dumps({"headline": headline})
    )
    await db_session.commit()
    return analysis, doc


async def test_get_analysis_resume(app_client, db_session):
    analysis, doc = await _fork(db_session)
    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "analysis" and body["content"]["headline"] == "Tailored for Acme"


async def test_get_analysis_resume_404_when_absent(app_client, db_session):
    analysis = await make_analysis(db_session, user_id=_USER_ID)
    await db_session.commit()
    assert (await app_client.get(f"/api/analysis/{analysis.id}/resume")).status_code == 404


async def test_fork_is_editable_via_content_patch(app_client, db_session):
    analysis, doc = await _fork(db_session)
    resp = await app_client.patch(
        f"/api/resume/{doc.id}/content",
        json={"base_rev": 0, "content": {"headline": "edited fork"}},
    )
    assert resp.status_code == 200 and resp.json()["rev"] == 1


async def test_save_to_master_clean_content_promotes(app_client, db_session):
    await make_profile(
        db_session,
        user_id=_USER_ID,
        profile_review_data="{}",
        yaml_data="Acme headline material",
        merged_profile="m",
    )
    await db_session.commit()
    (await app_client.get("/api/resume"))  # seed the Default master
    analysis, doc = await _fork(db_session, headline="")  # empty headline → no fabrications
    resp = await app_client.post(
        f"/api/analysis/{analysis.id}/resume/save-to-master", json={"name": "From Acme"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "master" and body["is_active"] is True and body["name"] == "From Acme"


async def test_save_to_master_flagged_requires_confirm(app_client, db_session):
    await make_profile(
        db_session,
        user_id=_USER_ID,
        profile_review_data="{}",
        yaml_data="plain profile",
        merged_profile="m",
    )
    await db_session.commit()
    (await app_client.get("/api/resume"))
    analysis, doc = await _fork(db_session, headline="Raised revenue 300% at Globex")
    blocked = await app_client.post(f"/api/analysis/{analysis.id}/resume/save-to-master", json={})
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert any(w["rule"] == "unsupported_metric" for w in detail["warnings"])
    confirmed = await app_client.post(
        f"/api/analysis/{analysis.id}/resume/save-to-master", json={"confirm": True}
    )
    assert confirmed.status_code == 200


async def test_analysis_resume_routes_require_auth(unauthenticated_client):
    for method, path in [
        ("GET", "/api/analysis/x/resume"),
        ("POST", "/api/analysis/x/resume/save-to-master"),
    ]:
        resp = await getattr(unauthenticated_client, method.lower())(
            path, **({"json": {}} if method == "POST" else {})
        )
        assert resp.status_code == 401


async def test_download_docx_serves_edited_fork(app_client, db_session):
    import io
    import zipfile

    from backend.models import JobResult

    analysis, doc = await _fork(db_session, headline="Original tailored")
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="resume_tailorer",
            output_json=json.dumps({"headline": "Original tailored"}),
        )
    )
    await db_session.commit()
    # edit the fork, then download — the DOCX must reflect the EDIT
    await app_client.patch(
        f"/api/resume/{doc.id}/content",
        json={"base_rev": 0, "content": {"headline": "Edited headline"}},
    )
    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume.docx")
    assert resp.status_code == 200
    # python-docx compresses the archive, so the literal string is not present in the
    # raw response bytes; unzip word/document.xml to inspect the actual content.
    xml = zipfile.ZipFile(io.BytesIO(resp.content)).read("word/document.xml")
    assert b"Edited headline" in xml
    assert b"Original tailored" not in xml
