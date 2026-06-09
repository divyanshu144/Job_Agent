from __future__ import annotations

import backend.models  # noqa: F401
from backend.models import Profile
from backend.services.auth_service import get_current_user
from tests.factories import make_user


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
