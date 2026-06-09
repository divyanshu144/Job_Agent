from __future__ import annotations

import io

from docx import Document

from backend.schemas import ResumeExperienceItem, ResumeTailorerOutput
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
    )

    body = render_resume_docx(output)

    document = Document(io.BytesIO(body))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Backend Engineer" in text
    assert "Python, PostgreSQL" in text
    assert "Built FastAPI services" in text
