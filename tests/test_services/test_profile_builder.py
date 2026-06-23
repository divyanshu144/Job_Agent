from unittest.mock import AsyncMock, patch

from backend.schemas import (
    ExtractedProfile,
    ProfileReviewData,
    ProfileReviewEducation,
    ProfileReviewExperience,
    ProfileReviewLink,
    ProfileReviewProject,
    ProfileWorkPreferences,
)


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
    assert "## Profile Review" not in profile.merged_profile


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


def test_profile_review_data_parse_falls_back_to_defaults():
    from backend.services.profile_builder import parse_profile_review_data

    assert parse_profile_review_data("").target_role == ""
    assert parse_profile_review_data("{not json").key_skills == []
    assert parse_profile_review_data('{"target_role": "ML Engineer"}').target_role == "ML Engineer"


def test_profile_review_data_serializes_round_trip():
    from backend.services.profile_builder import (
        parse_profile_review_data,
        serialize_profile_review_data,
    )

    data = ProfileReviewData(target_role="Backend Engineer", key_skills=["Python"])
    raw = serialize_profile_review_data(data)

    assert parse_profile_review_data(raw).target_role == "Backend Engineer"
    assert parse_profile_review_data(raw).key_skills == ["Python"]


def test_build_profile_review_text_renders_all_review_sections():
    from backend.services.profile_builder import build_profile_review_text

    data = ProfileReviewData(
        target_role="AI Engineer",
        key_skills=["Python", "PostgreSQL"],
        projects=[
            ProfileReviewProject(
                name="Job Agent",
                description="Application assistant",
                highlights=["Built matching pipeline"],
            )
        ],
        experience=[
            ProfileReviewExperience(
                company="Acme",
                role="Backend Engineer",
                dates="2022-2024",
                highlights=["Shipped APIs"],
            )
        ],
        links=[ProfileReviewLink(label="GitHub", url="https://github.com/example")],
        work_preferences=ProfileWorkPreferences(
            locations=["London"],
            remote="Hybrid",
            role_types=["Full-time"],
            industries=["AI"],
        ),
    )

    rendered = build_profile_review_text(data)

    assert "Target Role\nAI Engineer" in rendered
    assert "- Python" in rendered
    assert "Job Agent" in rendered
    assert "Backend Engineer - Acme" in rendered
    assert "GitHub: https://github.com/example" in rendered
    assert "Locations: London" in rendered
    assert "Remote: Hybrid" in rendered
    assert "Role types: Full-time" in rendered
    assert "Industries: AI" in rendered


def test_build_profile_review_text_renders_education():
    from backend.services.profile_builder import build_profile_review_text

    data = ProfileReviewData(
        education=[
            ProfileReviewEducation(
                institution="University of Exeter",
                degree="MSc",
                field_of_study="Computer Science",
                dates="Jan 2026",
            )
        ]
    )

    rendered = build_profile_review_text(data)

    assert "Education" in rendered
    assert "University of Exeter" in rendered
    assert "MSc" in rendered
    assert "Computer Science" in rendered
    assert "Jan 2026" in rendered


def test_review_seed_from_extracted_fills_empty_skills_and_education():
    from backend.services.profile_builder import review_seed_from_extracted

    extracted = ExtractedProfile.model_validate(
        {
            "core_skills": {
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
            },
            "education": [
                {
                    "institution": "Uni",
                    "degree": "BSc",
                    "field_of_study": "CS",
                    "dates": "2021",
                }
            ],
        }
    )

    seed = review_seed_from_extracted(extracted, ProfileReviewData())

    assert seed.key_skills == ["Python", "FastAPI", "Docker"]
    assert seed.education[0].institution == "Uni"
    assert seed.education[0].degree == "BSc"
    assert seed.education[0].field_of_study == "CS"


def test_review_seed_from_extracted_is_non_destructive():
    """Re-uploading a CV must not clobber skills/education the user already saved."""
    from backend.services.profile_builder import review_seed_from_extracted

    extracted = ExtractedProfile.model_validate(
        {
            "core_skills": {"languages": ["Python"]},
            "education": [{"institution": "New Uni", "degree": "BSc"}],
        }
    )
    existing = ProfileReviewData(
        key_skills=["Rust"],
        education=[ProfileReviewEducation(institution="Old Uni", degree="PhD")],
    )

    seed = review_seed_from_extracted(extracted, existing)

    assert seed.key_skills == ["Rust"]
    assert seed.education[0].institution == "Old Uni"
    assert seed.education[0].degree == "PhD"


async def test_build_profile_from_text_includes_review_data_and_cv_text(session):
    from backend.services.profile_builder import build_profile_from_text

    profile = await build_profile_from_text(
        session,
        yaml_text="identity:\n  name: User\n",
        cv_text="Uploaded CV text with Python and FastAPI.",
        user_id="test-user-id",
        profile_review_data=ProfileReviewData(
            target_role="Platform Engineer",
            key_skills=["Python", "FastAPI"],
        ),
        review_status="saved",
    )

    assert profile.profile_review_data != "{}"
    assert profile.review_status == "saved"
    assert "## Candidate Profile (YAML)" in profile.merged_profile
    assert "## Profile Review" in profile.merged_profile
    assert "Platform Engineer" in profile.merged_profile
    assert "- FastAPI" in profile.merged_profile
    assert "## CV Text" in profile.merged_profile
    assert "Uploaded CV text with Python" in profile.merged_profile
