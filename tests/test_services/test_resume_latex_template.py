from __future__ import annotations

import pytest

from backend.schemas import (
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeProjectItem,
    ResumeTailorerOutput,
)
from backend.services.resume_latex_template import (
    _limit_words,
    escape_latex,
    render_resume_latex,
)


def test_escape_latex_escapes_user_and_model_text() -> None:
    assert escape_latex("Python & SQL_100% #1") == r"Python \& SQL\_100\% \#1"


def test_limit_words_under_budget_returned_whole() -> None:
    assert _limit_words("Built the API gateway.", 10) == "Built the API gateway."


def test_limit_words_never_chops_a_single_sentence_midway() -> None:
    """A single sentence longer than the budget is kept whole, never cut mid-clause
    with a fabricated period (the 'giving the team better.' bug)."""
    bullet = (
        "Raised automation test coverage by forty percent using Selenium and Java "
        "giving the team better regression confidence on every release"
    )

    out = _limit_words(bullet, 8)

    assert out == bullet
    assert not out.endswith("Java.")


def test_limit_words_keeps_only_whole_sentences_within_budget() -> None:
    """When the text has multiple sentences, drop whole trailing sentences rather
    than amputating one."""
    text = "Built the API. Cut load times by twenty percent overall. Mentored engineers."

    out = _limit_words(text, 6)

    assert out == "Built the API."


def test_render_resume_latex_fills_format_without_mutating_resume_source() -> None:
    output = ResumeTailorerOutput(
        headline="Backend Engineer",
        summary="Builds APIs, retrieval systems, and production workflows.",
        skills=["Python", "FastAPI", "PostgreSQL", "RAG & evals"],
        experience=[
            ResumeExperienceItem(
                company="Acme",
                role="Software Engineer",
                dates="2022-2024",
                bullets=["Built FastAPI services with 20% faster page loads."],
            )
        ],
        projects=[
            ResumeProjectItem(
                name="JobFit Agent",
                description="FastAPI, React",
                bullets=["Built role review and resume tailoring workflow."],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="University of Exeter",
                degree="MSc Statistical Data Science",
                dates="2026",
            )
        ],
    )

    tex = render_resume_latex(
        output,
        template=(
            r"\section{Professional Summary}"
            "\n"
            "%%JOBFIT_SUMMARY%%\n"
            r"\section{Experience}"
            "\n"
            "%%JOBFIT_EXPERIENCE%%\n"
            r"\section{Projects}"
            "\n"
            "%%JOBFIT_PROJECTS%%\n"
            r"\begin{tabular}{ll}"
            "\n"
            "%%JOBFIT_SKILLS%%\n"
            r"\end{tabular}"
            "\n"
            r"\section{Education}"
            "\n"
            "%%JOBFIT_EDUCATION%%\n"
        ),
    )

    assert "%%JOBFIT_" not in tex
    assert "Builds APIs, retrieval systems" in tex
    assert r"RAG \& evals" in tex
    assert r"\resumeheading{Acme}{}{Software Engineer}{2022-2024}" in tex
    assert r"\projectheading{JobFit Agent}{FastAPI, React}{}" in tex


def test_render_resume_latex_raises_for_unfilled_marker() -> None:
    with pytest.raises(RuntimeError):
        render_resume_latex(ResumeTailorerOutput(summary="x"), template="%%JOBFIT_UNKNOWN%%")
