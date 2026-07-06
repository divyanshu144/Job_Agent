from __future__ import annotations

import io

from docx import Document

from backend.schemas import (
    BulletItem,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeProjectItem,
    ResumeTailorerOutput,
)
from backend.services.resume_docx import render_resume_docx


def test_render_resume_docx_outputs_valid_docx_with_content() -> None:
    output = ResumeTailorerOutput(
        headline="Backend Engineer",
        summary="Builds reliable APIs.",
        skills=["Python", "PostgreSQL"],
        experience=[
            ResumeExperienceItem(
                company="Acme",
                role="Engineer",
                dates="2022-2024",
                bullets=["Built FastAPI services", "Improved SQL performance"],
            )
        ],
        projects=[
            ResumeProjectItem(
                name="JobFit",
                description="Application support platform",
                bullets=["Generated tailored application materials"],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="Example University",
                degree="BSc Computer Science",
                dates="2020",
            )
        ],
        tailored_bullets=[
            BulletItem(
                original="Built APIs",
                rewritten="Built reliable FastAPI services for production workflows",
                rationale="More specific",
            )
        ],
    )

    body = render_resume_docx(output)

    document = Document(io.BytesIO(body))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Backend Engineer" in text
    assert "Python, PostgreSQL" in text
    assert "Built FastAPI services" in text
    assert "JobFit" in text
    assert "Generated tailored application materials" in text
    assert "BSc Computer Science - Example University (2020)" in text
    # tailored_bullets are rewrite-explanation metadata; their rewrites are already
    # placed in Experience/Projects, so rendering them again duplicates content and
    # pushes the DOCX to two pages. They must NOT appear in the document.
    assert "Additional Highlights" not in text
    assert "Built reliable FastAPI services for production workflows" not in text
