from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.models import Analysis, JobResult, Profile
from tests.factories import make_analysis, make_profile, make_user

_USER_ID = "test-user-id"  # matches conftest._FAKE_USER (the auth override)


@pytest.fixture
async def client_with_data(app_client, Session):
    async with Session() as s:
        # The auth user (_USER_ID) is seeded by conftest; seed parents before children.
        p = Profile(
            yaml_data="x",
            cv_text="",
            merged_profile="x",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(p)
        await s.flush()
        a = Analysis(
            jd_text="Senior ML Engineer " * 5,
            profile_id=p.id,
            partial=False,
            user_id=_USER_ID,
            role_type="ML Engineer",
            company="Acme Corp",
            match_score=80,
        )
        s.add(a)
        await s.flush()
        s.add(
            JobResult(
                analysis_id=a.id, agent_name="match_scorer", output_json=json.dumps({"score": 80})
            )
        )
        await s.commit()
        analysis_id = a.id

    return app_client, analysis_id


async def test_list_history(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


async def test_get_analysis_detail(client_with_data):
    client, analysis_id = client_with_data
    resp = await client.get(f"/api/analysis/{analysis_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == analysis_id
    assert "match_scorer" in data["results"]
    assert data["result_errors"] == {}


async def test_get_analysis_detail_includes_failed_agent_errors(app_client, db_session):
    profile = await make_profile(db_session, user_id=_USER_ID)
    analysis = await make_analysis(db_session, profile=profile, user_id=_USER_ID)
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="resume_tailorer",
            error="resume_tailorer: invalid JSON",
        )
    )
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == {}
    assert data["result_errors"]["resume_tailorer"] == "resume_tailorer: invalid JSON"


async def test_history_pagination(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history?limit=0&offset=0")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_history_includes_denormalized_meta(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["role_type"] == "ML Engineer"
    assert item["company"] == "Acme Corp"
    assert item["match_score"] == 80


async def test_history_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/history")
    assert resp.status_code == 401


async def test_get_analysis_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(
        db_session, id="other-history-user", email="other-history@example.com"
    )
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other_user.id)
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}")

    assert resp.status_code == 404


async def test_download_resume_docx_for_owned_analysis(app_client, db_session):
    profile = await make_profile(db_session, user_id=_USER_ID)
    analysis = await make_analysis(db_session, profile=profile, user_id=_USER_ID)
    db_session.add(
        JobResult(
            analysis_id=analysis.id,
            agent_name="resume_tailorer",
            output_json=json.dumps(
                {
                    "headline": "Backend Engineer",
                    "summary": "Builds APIs.",
                    "skills": ["Python"],
                    "experience": [
                        {
                            "company": "Acme",
                            "role": "Engineer",
                            "dates": "2022-2024",
                            "bullets": ["Built FastAPI services"],
                        }
                    ],
                    "projects": [],
                    "education": [],
                    "tailored_bullets": [],
                    "omitted_items": [],
                }
            ),
        )
    )
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume.docx")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert resp.content.startswith(b"PK")


async def test_download_resume_docx_rejects_cross_user_analysis(app_client, db_session):
    other_user = await make_user(
        db_session, id="other-resume-user", email="other-resume@example.com"
    )
    profile = await make_profile(db_session, user_id=other_user.id)
    analysis = await make_analysis(db_session, profile=profile, user_id=other_user.id)
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume.docx")

    assert resp.status_code == 404


async def test_download_resume_docx_requires_generated_resume(app_client, db_session):
    profile = await make_profile(db_session, user_id=_USER_ID)
    analysis = await make_analysis(db_session, profile=profile, user_id=_USER_ID)
    await db_session.commit()

    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume.docx")

    assert resp.status_code == 404
