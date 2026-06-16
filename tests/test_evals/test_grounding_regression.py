from __future__ import annotations

from backend.evals.validators import validate_cover_letter, validate_resume_tailorer
from backend.schemas import (
    CoverLetterOutput,
    JobParserOutput,
    PriorOutputs,
    ResumeExperienceItem,
    ResumeTailorerOutput,
)


def test_resume_tailorer_omits_unsupported_fixture_claims():
    output = ResumeTailorerOutput(
        summary="Backend engineer",
        skills=["Python", "Kubernetes"],
        experience=[
            ResumeExperienceItem(
                company="Invented Labs",
                role="Engineer",
                bullets=["Built Python APIs and owned Kubernetes production clusters"],
            )
        ],
    )

    warnings = validate_resume_tailorer(
        output,
        PriorOutputs(),
        source_text=(
            "## CV Text\nSynthetic Candidate. Skills: Python. "
            "Experience: Built Python APIs."
        ),
    )

    assert output.skills == ["Python"]
    assert output.experience[0].company is None
    assert any(w.rule == "unsupported_skill_omitted" for w in warnings)
    assert any(w.rule == "unsupported_employer_omitted" for w in warnings)
    assert any(w.rule == "unsupported_bullet_skill" for w in warnings)


def test_cover_letter_required_skill_warning_is_surfaced():
    prior = PriorOutputs(
        job_parser=JobParserOutput(
            required_skills=["Python"],
            nice_to_have=[],
            role_type="Backend Engineer",
            seniority="Senior",
        )
    )
    output = CoverLetterOutput(
        subject="Application",
        body=" ".join(["general"] * 160),
        tone_notes="generic",
    )

    warnings = validate_cover_letter(output, prior)

    assert any(w.rule == "no_required_skills_mentioned" for w in warnings)
