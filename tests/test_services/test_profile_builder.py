from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.database import Base


@pytest_asyncio.fixture(loop_scope="function")
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_build_profile_merges_sources(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Test User\ncore_skills:\n  languages: [Python]\n")

    with patch(
        "backend.services.profile_builder.extract_text_from_file", new_callable=AsyncMock
    ) as mock_cv:
        mock_cv.return_value = "Experienced Python developer"
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(yaml_path), "fake/cv.pdf")

    assert profile.id is not None
    assert "Test User" in profile.yaml_data
    assert profile.cv_text == "Experienced Python developer"
    assert "## Candidate Profile" in profile.merged_profile
    assert "CV Text" in profile.merged_profile


async def test_build_profile_no_cv(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: No CV\n")

    with patch(
        "backend.services.profile_builder.extract_text_from_file", new_callable=AsyncMock
    ) as mock_cv:
        mock_cv.return_value = ""
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(yaml_path), "fake/cv.pdf")

    assert "No CV" in profile.yaml_data
    assert "CV Text" not in profile.merged_profile


async def test_get_or_build_returns_cached(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Cached\n")

    with patch(
        "backend.services.profile_builder.extract_text_from_file",
        new_callable=AsyncMock,
        return_value="",
    ):
        from backend.services.profile_builder import build_profile

        p1 = await build_profile(session, str(yaml_path), "fake/cv.pdf")
        assert p1.id is not None


async def test_get_or_build_creates_when_none(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: New\n")

    with (
        patch(
            "backend.services.profile_builder.extract_text_from_file",
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
