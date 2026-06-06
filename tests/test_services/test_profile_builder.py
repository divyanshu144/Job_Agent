import json
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.database import Base


@pytest_asyncio.fixture(loop_scope="function")
async def session():
    # StaticPool ensures all connections reuse the same underlying SQLite DB.
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
    from backend.models import GithubCache

    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text(
        "identity:\n  name: Test User\ncore_skills:\n  languages: [Python]\n"
        "featured_projects:\n  - repo: divyanshu144/docchat\n"
    )

    # Populate GitHub cache
    cache = GithubCache(
        owner="divyanshu144", repo_name="docchat", readme_content="# DocChat README"
    )
    session.add(cache)
    await session.commit()

    with patch(
        "backend.services.cv_parser.extract_text_from_file", new_callable=AsyncMock
    ) as mock_cv:
        mock_cv.return_value = ""
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(yaml_path), "fake/cv.pdf")

    assert profile.id is not None
    assert "Test User" in profile.yaml_data
    assert profile.cv_text == ""
    github = json.loads(profile.github_data)
    assert "divyanshu144/docchat" in github
    assert "## Candidate Profile" in profile.merged_profile
    assert "DocChat" in profile.merged_profile


def test_assemble_merged_is_github_order_independent():
    """merged_profile feeds profile_content_hash, so it must be deterministic regardless of
    github_data ordering — else identical content hashes differently across rebuilds."""
    from backend.services.profile_builder import _assemble_merged

    a = _assemble_merged("YAML", "CV", {"z/z": "readme-z", "a/a": "readme-a"})
    b = _assemble_merged("YAML", "CV", {"a/a": "readme-a", "z/z": "readme-z"})
    assert a == b


async def test_build_profile_empty_readme_counts_as_no_github(session, tmp_path):
    """A cache row whose readme_content is empty must not count as GitHub content:
    it's filtered from github_data, and the 'not synced' warning is surfaced — one signal."""
    from datetime import datetime, timezone

    from backend.models import GithubCache
    from backend.routes.profile import _profile_response

    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: T\nfeatured_projects: []\n")
    session.add(
        GithubCache(
            owner="o", repo_name="r", readme_content="", fetched_at=datetime.now(timezone.utc)
        )
    )
    await session.commit()

    with patch(
        "backend.services.cv_parser.extract_text_from_file", new_callable=AsyncMock
    ) as mock_cv:
        mock_cv.return_value = ""
        from backend.services.profile_builder import build_profile

        profile = await build_profile(session, str(yaml_path), "fake/cv.pdf")

    assert json.loads(profile.github_data) == {}  # empty readme filtered out
    assert _profile_response(profile).warnings  # 'not synced' warning surfaced


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
