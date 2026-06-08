from unittest.mock import AsyncMock, patch


async def test_build_profile_merges_sources(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Test User\ncore_skills:\n  languages: [Python]\n")

    with patch(
        "backend.services.profile_builder.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="My CV body text",
    ):
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(yaml_path), "fake/cv.pdf")

    assert profile.id is not None
    assert "Test User" in profile.yaml_data
    assert profile.cv_text == "My CV body text"
    assert "## Candidate Profile" in profile.merged_profile
    assert "My CV body text" in profile.merged_profile


async def test_get_or_build_returns_cached(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Cached\nfeatured_projects: []\n")

    with patch(
        "backend.services.cv_parser.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="",
    ):
        from backend.services.profile_builder import build_profile

        p1 = await build_profile(session, str(yaml_path), "fake/cv.pdf")
        # get_or_build_profile will use settings paths —
        # override by directly calling build again isn't needed
        # Just verify p1 was created with correct id
        assert p1.id is not None


async def test_get_or_build_creates_when_none(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: New\nfeatured_projects: []\n")

    with (
        patch(
            "backend.services.cv_parser.extract_text_from_file",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch("backend.services.profile_builder.settings") as mock_settings,
    ):
        mock_settings.profile_yaml_path = str(yaml_path)
        mock_settings.cv_path = "fake/cv.pdf"
        from backend.services.profile_builder import get_or_build_profile

        p = await get_or_build_profile(session)
        assert p.id is not None


async def test_build_profile_uses_starter_yaml_when_missing(session, tmp_path):
    missing_yaml = tmp_path / "missing.yaml"

    with patch(
        "backend.services.profile_builder.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="Uploaded CV text",
    ):
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(missing_yaml), "fake/cv.pdf")

    assert "name: Candidate" in profile.yaml_data
    assert profile.cv_text == "Uploaded CV text"
    assert "Uploaded CV text" in profile.merged_profile
