from __future__ import annotations

import backend.models  # noqa: F401


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
