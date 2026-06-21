from __future__ import annotations

import json

from sqlalchemy import select

import backend.models  # noqa: F401
from backend.models import Profile
from backend.services.auth_service import get_current_user
from tests.factories import make_user


def _review_payload() -> dict:
    return {
        "review_data": {
            "target_role": "Backend Platform Engineer",
            "key_skills": ["Python", "PostgreSQL", "FastAPI"],
            "projects": [
                {
                    "name": "Job Agent",
                    "description": "Built an async job application assistant.",
                    "highlights": ["Added profile review flow"],
                }
            ],
            "experience": [
                {
                    "company": "Acme",
                    "role": "Software Engineer",
                    "dates": "2022-2025",
                    "highlights": ["Shipped production APIs"],
                }
            ],
            "links": [{"label": "GitHub", "url": "https://github.com/example"}],
            "work_preferences": {
                "locations": ["London"],
                "remote": "Hybrid",
                "role_types": ["Full-time"],
                "industries": ["Developer tools"],
            },
        }
    }


async def test_get_profile_builds_on_first_call(app_client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.services.cv_parser.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await app_client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "merged_profile" in data


async def test_profile_refresh(app_client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.services.cv_parser.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await app_client.post("/api/profile/refresh")
    assert resp.status_code == 200
    assert "last_refreshed_at" in resp.json()


async def test_profile_refresh_preserves_uploaded_user_cv_without_global_fallback(
    app_client, db_session
):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch

    user_b = await make_user(db_session, id="user-b", email="user-b@example.com")
    db_session.add_all(
        [
            Profile(
                yaml_data="identity:\n  name: User A\n",
                cv_text="User A uploaded CV with Python and SQL experience.",
                merged_profile="User A profile\nUser A uploaded CV",
                last_refreshed_at=datetime.now(timezone.utc),
                user_id="test-user-id",
            ),
            Profile(
                yaml_data="identity:\n  name: User B\n",
                cv_text="User B private CV with Java and Kotlin experience.",
                merged_profile="User B profile\nUser B private CV",
                last_refreshed_at=datetime.now(timezone.utc),
                user_id=user_b.id,
            ),
        ]
    )
    await db_session.commit()

    with patch(
        "backend.services.profile_builder.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="Global CV text that must not be used.",
    ) as extract_text:
        resp = await app_client.post("/api/profile/refresh")

    assert resp.status_code == 200
    assert resp.json()["cv_text"] == "User A uploaded CV with Python and SQL experience."
    assert "User A uploaded CV with Python" in resp.json()["merged_profile"]
    assert "Global CV text" not in resp.json()["merged_profile"]
    assert "User B private CV" not in resp.json()["merged_profile"]
    extract_text.assert_not_called()


async def test_profile_review_requires_authentication(unauthenticated_client):
    get_resp = await unauthenticated_client.get("/api/profile/review")
    put_resp = await unauthenticated_client.put("/api/profile/review", json=_review_payload())

    assert get_resp.status_code == 401
    assert put_resp.status_code == 401


async def test_get_profile_review_creates_default_without_reading_global_cv(app_client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.services.profile_builder.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="Global CV text that must not be read.",
    ) as extract_text:
        resp = await app_client.get("/api/profile/review")

    assert resp.status_code == 200
    data = resp.json()
    assert data["review_data"] == {
        "target_role": "",
        "key_skills": [],
        "projects": [],
        "experience": [],
        "links": [],
        "work_preferences": {
            "locations": [],
            "remote": None,
            "role_types": [],
            "industries": [],
        },
    }
    assert data["review_status"] == "draft"
    assert data["reviewed_at"] is None
    assert data["has_cv_text"] is False
    extract_text.assert_not_called()


async def test_get_profile_review_returns_existing_user_review(app_client, db_session):
    from datetime import datetime, timezone

    reviewed_at = datetime.now(timezone.utc)
    db_session.add(
        Profile(
            yaml_data="identity:\n  name: User A\n",
            cv_text="User A CV text",
            merged_profile="User A merged",
            profile_review_data=json.dumps(
                {
                    "target_role": "ML Engineer",
                    "key_skills": ["Python"],
                    "projects": [],
                    "experience": [],
                    "links": [],
                    "work_preferences": {},
                }
            ),
            review_status="saved",
            reviewed_at=reviewed_at,
            last_refreshed_at=reviewed_at,
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    resp = await app_client.get("/api/profile/review")

    assert resp.status_code == 200
    data = resp.json()
    assert data["review_data"]["target_role"] == "ML Engineer"
    assert data["review_data"]["key_skills"] == ["Python"]
    assert data["review_status"] == "saved"
    assert data["reviewed_at"] is not None
    assert data["has_cv_text"] is True


async def test_put_profile_review_saves_all_editable_fields(app_client):
    resp = await app_client.put("/api/profile/review", json=_review_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["review_status"] == "saved"
    assert data["reviewed_at"] is not None
    assert data["has_cv_text"] is False
    assert data["review_data"] == _review_payload()["review_data"]


async def test_put_profile_review_rebuilds_merged_profile_with_cv(app_client, db_session):
    from datetime import datetime, timezone

    db_session.add(
        Profile(
            yaml_data="identity:\n  name: User A\n",
            cv_text="User A uploaded CV with Python and SQL experience.",
            merged_profile="Old merged profile",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    resp = await app_client.put("/api/profile/review", json=_review_payload())

    assert resp.status_code == 200
    profile_id = resp.json()["profile_id"]
    profile = (
        await db_session.execute(select(Profile).where(Profile.id == profile_id))
    ).scalar_one()
    assert profile.review_status == "saved"
    assert profile.reviewed_at is not None
    assert "## Profile Review" in profile.merged_profile
    assert "Backend Platform Engineer" in profile.merged_profile
    assert "- Python" in profile.merged_profile
    assert "Job Agent" in profile.merged_profile
    assert "Acme" in profile.merged_profile
    assert "GitHub: https://github.com/example" in profile.merged_profile
    assert "Locations: London" in profile.merged_profile
    assert "## CV Text" in profile.merged_profile
    assert "User A uploaded CV with Python" in profile.merged_profile


async def test_profile_review_is_user_isolated(app_client, db_session):
    from datetime import datetime, timezone

    from backend.main import app

    user_b = await make_user(db_session, id="user-b", email="user-b-review@example.com")
    user_b_profile = Profile(
        yaml_data="identity:\n  name: User B\n",
        cv_text="User B private CV",
        merged_profile="User B merged",
        profile_review_data=json.dumps({"target_role": "Private User B Role"}),
        review_status="saved",
        reviewed_at=datetime.now(timezone.utc),
        last_refreshed_at=datetime.now(timezone.utc),
        user_id=user_b.id,
    )
    db_session.add(user_b_profile)
    await db_session.commit()

    get_resp = await app_client.get("/api/profile/review")
    assert get_resp.status_code == 200
    assert get_resp.json()["review_data"]["target_role"] != "Private User B Role"

    put_resp = await app_client.put("/api/profile/review", json=_review_payload())
    assert put_resp.status_code == 200
    assert put_resp.json()["review_data"]["target_role"] == "Backend Platform Engineer"

    previous_override = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp_b = await app_client.get("/api/profile/review")
    finally:
        app.dependency_overrides[get_current_user] = previous_override

    assert resp_b.status_code == 200
    assert resp_b.json()["review_data"]["target_role"] == "Private User B Role"


async def test_cv_upload_is_user_isolated(app_client, db_session):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch

    from backend.main import app

    db_session.add(
        Profile(
            yaml_data="identity:\n  name: User A\n",
            cv_text="User A old CV",
            merged_profile="User A profile\nUser A old CV",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    user_b = await make_user(db_session, id="user-b", email="user-b@example.com")
    db_session.add(
        Profile(
            yaml_data="identity:\n  name: User B\n",
            cv_text="User B private CV",
            merged_profile="User B profile\nUser B private CV",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id=user_b.id,
        )
    )
    await db_session.commit()

    with patch(
        "backend.routes.profile.extract_text_from_pdf_bytes",
        new_callable=AsyncMock,
        return_value="User A private CV with Python and SQL experience.",
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200
    assert resp.json()["cv_text"] == "User A private CV with Python and SQL experience."

    previous_override = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp_b = await app_client.get("/api/profile")
    finally:
        app.dependency_overrides[get_current_user] = previous_override

    assert resp_b.status_code == 200
    assert resp_b.json()["cv_text"] == "User B private CV"


async def test_docx_upload_extracts_text(app_client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routes.profile.extract_text_from_docx_bytes",
        new_callable=AsyncMock,
        return_value="DOCX resume text with Python and PostgreSQL experience.",
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={
                "file": (
                    "resume.docx",
                    b"fake-docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert resp.status_code == 200
    assert resp.json()["cv_text"] == "DOCX resume text with Python and PostgreSQL experience."
    assert resp.json()["profile_review_data"] == "{}"
    assert resp.json()["review_status"] == "draft"
    assert "DOCX resume text with Python" in resp.json()["merged_profile"]

    review_resp = await app_client.get("/api/profile/review")
    assert review_resp.status_code == 200
    assert review_resp.json()["has_cv_text"] is True
    assert review_resp.json()["review_status"] == "draft"


async def test_upload_rejects_near_empty_extraction(app_client):
    from unittest.mock import AsyncMock, patch

    with patch(
        "backend.routes.profile.extract_text_from_pdf_bytes",
        new_callable=AsyncMock,
        return_value="Name",
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 400
    assert "extract enough resume text" in resp.json()["detail"]


async def test_cv_upload_populates_yaml_from_extractor(app_client):
    from unittest.mock import AsyncMock, patch

    from backend.schemas import ExtractedProfile

    extracted = ExtractedProfile.model_validate(
        {
            "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
            "core_skills": {"languages": ["Python"], "frameworks": ["FastAPI"], "tools": []},
            "experience": [],
            "featured_projects": [],
        }
    )

    with (
        patch(
            "backend.routes.profile.extract_text_from_pdf_bytes",
            new_callable=AsyncMock,
            return_value="Ada Lovelace ML Engineer with Python and FastAPI experience.",
        ),
        patch(
            "backend.routes.profile.ProfileExtractorAgent.run",
            new_callable=AsyncMock,
            return_value=extracted,
        ),
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200
    yaml_data = resp.json()["yaml_data"]
    assert "Ada Lovelace" in yaml_data
    assert "Python" in yaml_data
    assert "FastAPI" in yaml_data


async def test_cv_upload_preserves_yaml_when_extractor_fails(app_client, db_session):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch

    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Existing Hand Edited\n",
            cv_text="old cv",
            merged_profile="old merged",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    with (
        patch(
            "backend.routes.profile.extract_text_from_pdf_bytes",
            new_callable=AsyncMock,
            return_value="New resume text with Python and SQL experience.",
        ),
        patch(
            "backend.routes.profile.ProfileExtractorAgent.run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ),
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200
    assert resp.json()["yaml_data"] == "identity:\n  name: Existing Hand Edited\n"
    assert resp.json()["cv_text"] == "New resume text with Python and SQL experience."


async def test_put_profile_yaml_persists_for_user(app_client, db_session):
    resp = await app_client.put(
        "/api/profile/yaml",
        json={"yaml_text": "identity:\n  name: Edited By User\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["yaml_data"] == "identity:\n  name: Edited By User\n"
    assert "Edited By User" in resp.json()["merged_profile"]


async def test_put_profile_yaml_rejects_invalid_yaml(app_client):
    resp = await app_client.put(
        "/api/profile/yaml",
        json={"yaml_text": "identity:\n  name: [unclosed\n"},
    )
    assert resp.status_code == 422
    assert "YAML" in resp.json()["detail"]


async def test_put_profile_yaml_requires_authentication(unauthenticated_client):
    resp = await unauthenticated_client.put(
        "/api/profile/yaml", json={"yaml_text": "identity:\n  name: X\n"}
    )
    assert resp.status_code == 401
