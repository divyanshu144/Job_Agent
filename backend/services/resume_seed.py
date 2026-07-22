from __future__ import annotations

import json

from backend.models import Profile
from backend.schemas import (
    ProfileReviewData,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeProjectItem,
    ResumeTailorerOutput,
)


def seed_resume_content(profile: Profile) -> ResumeTailorerOutput:
    """Deterministically map the user's reviewed profile into a base resume.

    No LLM: the master resume is a curated *view* of the profile, editable after.
    """
    raw = profile.profile_review_data or "{}"
    review = ProfileReviewData.model_validate(json.loads(raw))

    experience = [
        ResumeExperienceItem(
            company=e.company or None,
            role=e.role or None,
            dates=e.dates or None,
            bullets=list(e.highlights),
        )
        for e in review.experience
    ]
    projects = [
        ResumeProjectItem(
            name=p.name, description=p.description or None, bullets=list(p.highlights)
        )
        for p in review.projects
    ]
    education = [
        ResumeEducationItem(
            institution=ed.institution or None,
            degree=(
                f"{ed.degree}, {ed.field_of_study}".strip(", ") if ed.field_of_study else ed.degree
            )
            or None,
            dates=ed.dates or None,
        )
        for ed in review.education
    ]
    return ResumeTailorerOutput(
        headline=review.target_role or "",
        summary="",
        skills=list(review.key_skills),
        experience=experience,
        projects=projects,
        education=education,
    )
