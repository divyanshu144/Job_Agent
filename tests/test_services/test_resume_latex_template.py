from __future__ import annotations

import pytest

from backend.schemas import (
    ProfileReviewLink,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeIdentity,
    ResumeProjectItem,
    ResumeTailorerOutput,
)
from backend.services.resume_latex_template import (
    _limit_words,
    escape_latex,
    load_latex_format,
    render_resume_latex,
)


def test_latex_format_template_has_ats_text_layer_directives() -> None:
    """The PDF text layer must extract cleanly for ATS parsers — guard the directives
    that fix f-ligature drop ('fixed'->'xed', 'flagged'->'agged'). Removing any of
    these regresses ATS-readability, which is invisible in the rendered image."""
    src = load_latex_format()
    assert "\\input{glyphtounicode}" in src
    assert "\\pdfgentounicode=1" in src
    assert "\\DisableLigatures" in src


def test_latex_format_template_has_no_hardcoded_identity() -> None:
    """The shipped template must not bake in one person's name/contact — every user's
    resume header is filled from their own profile."""
    src = load_latex_format()
    assert "DIVYANSHU" not in src.upper()
    assert "divyanshucharak" not in src.lower()
    assert "%%JOBFIT_HEADER%%" in src


def test_render_resume_latex_header_uses_user_identity() -> None:
    identity = ResumeIdentity(
        name="Ada Lovelace",
        location="London, UK",
        email="ada@example.com",
        phone="+44 7000 000000",
        links=[ProfileReviewLink(label="GitHub", url="https://github.com/ada")],
    )

    tex = render_resume_latex(
        ResumeTailorerOutput(summary="Builds systems."),
        identity=identity,
        template="%%JOBFIT_HEADER%%\n%%JOBFIT_SUMMARY%%",
    )

    assert "Ada Lovelace" in tex
    assert "ada@example.com" in tex
    assert "github.com/ada" in tex
    assert "+44 7000 000000" in tex
    assert "DIVYANSHU" not in tex.upper()


def test_render_resume_latex_header_omits_empty_fields() -> None:
    identity = ResumeIdentity(name="Ada Lovelace", email="ada@example.com")

    tex = render_resume_latex(
        ResumeTailorerOutput(summary="x"),
        identity=identity,
        template="%%JOBFIT_HEADER%%\n%%JOBFIT_SUMMARY%%",
    )

    assert "Ada Lovelace" in tex
    # no stray separators for absent phone/location/links
    assert "$\\cdot$ $\\cdot$" not in tex


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


def _many_section_output() -> ResumeTailorerOutput:
    """Content that overflows every default cap (summary words, 3 experiences,
    3 bullets/role, 24 skills) so faithful-vs-capped rendering is observable."""
    long_summary = " ".join(f"Sentence number {i} about impact." for i in range(1, 40))
    return ResumeTailorerOutput(
        headline="Staff Backend Engineer",
        summary=long_summary,
        skills=[f"Skill{i}" for i in range(1, 31)],  # 30 > 24 cap
        experience=[
            ResumeExperienceItem(
                company=f"Company{i}",
                role="Engineer",
                dates="2020-2024",
                bullets=[f"Achievement bullet number {b} at company {i}." for b in range(1, 6)],
            )
            for i in range(1, 6)  # 5 roles > 3 cap; 5 bullets/role > 3 cap
        ],
    )


def test_faithful_render_keeps_all_content_uncapped() -> None:
    """The WYSIWYG download must never drop the user's curated content: every
    experience, every bullet, every skill, and the full summary survive."""
    output = _many_section_output()

    tex = render_resume_latex(output, faithful=True)

    assert "Sentence number 39 about impact." in tex  # full summary, not truncated
    assert "Company5" in tex  # 5th role kept (default caps at 3)
    assert "Skill30" in tex  # 30th skill kept (default caps at 24)
    assert "Achievement bullet number 5 at company 5." in tex  # 5th bullet kept


def test_default_render_still_caps_content() -> None:
    """The auto-generated one-page path keeps its caps — faithful mode is opt-in."""
    output = _many_section_output()

    tex = render_resume_latex(output)  # faithful defaults to False

    assert "Company4" not in tex  # only first 3 roles
    assert "Skill30" not in tex  # skills capped at 24


def test_faithful_render_surfaces_edited_headline_as_tagline() -> None:
    """A headline edited in the resume editor must reach the PDF header, but is
    suppressed when it merely repeats the name."""
    identity = ResumeIdentity(name="Ada Lovelace")

    with_tagline = render_resume_latex(
        ResumeTailorerOutput(headline="Staff Backend Engineer", summary="x"),
        identity=identity,
        template="%%JOBFIT_HEADER%%\n%%JOBFIT_SUMMARY%%",
    )
    assert "Staff Backend Engineer" in with_tagline

    no_tagline = render_resume_latex(
        ResumeTailorerOutput(headline="Ada Lovelace", summary="x"),
        identity=identity,
        template="%%JOBFIT_HEADER%%\n%%JOBFIT_SUMMARY%%",
    )
    assert no_tagline.count("Ada Lovelace") == 1  # no duplicate name line
