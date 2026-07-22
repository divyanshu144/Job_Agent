from backend.models import Profile
from backend.schemas import ProfileReviewData
from backend.services.resume_seed import seed_resume_content


def _profile_with(review: ProfileReviewData) -> Profile:
    return Profile(
        yaml_data="x",
        merged_profile="m",
        profile_review_data=review.model_dump_json(),
    )


def test_seed_maps_profile_sections():
    review = ProfileReviewData(
        target_role="Senior Backend Engineer",
        key_skills=["Python", "FastAPI"],
        experience=[
            {
                "company": "Acme",
                "role": "SWE",
                "dates": "2022-2024",
                "highlights": ["Built X", "Owned Y"],
            }
        ],
        projects=[{"name": "JobFit", "description": "AI app", "highlights": ["pipeline"]}],
        education=[
            {"institution": "PES", "degree": "BSc", "field_of_study": "CS", "dates": "2017-2021"}
        ],
    )
    out = seed_resume_content(_profile_with(review))
    assert out.headline == "Senior Backend Engineer"
    assert out.skills == ["Python", "FastAPI"]
    assert out.experience[0].company == "Acme"
    assert out.experience[0].bullets == ["Built X", "Owned Y"]
    assert out.projects[0].name == "JobFit"
    assert out.projects[0].bullets == ["pipeline"]
    assert out.education[0].institution == "PES"


def test_seed_handles_empty_review():
    out = seed_resume_content(Profile(yaml_data="x", merged_profile="m", profile_review_data="{}"))
    assert out.headline == ""
    assert out.experience == []
