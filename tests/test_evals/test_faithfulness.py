from __future__ import annotations

from backend.evals.faithfulness import validate_resume_faithfulness
from backend.schemas import ResumeTailorerOutput

_SOURCE = """
## Candidate Profile (YAML)
Worked at Acme Corp as a Software Engineer, 2022-2024.
Built the billing pipeline; cut p99 latency by 40 percent (40%).
Skills: Python, FastAPI, PostgreSQL.
BSc Computer Science, PES University, 2017-2021.
"""


def _content(**overrides) -> ResumeTailorerOutput:
    base = {
        "headline": "Software Engineer",
        "summary": "Engineer with Python experience.",
        "skills": ["Python"],
        "experience": [
            {
                "company": "Acme Corp",
                "role": "Software Engineer",
                "dates": "2022-2024",
                "bullets": ["Built the billing pipeline"],
            }
        ],
        "education": [{"institution": "PES University", "degree": "BSc", "dates": "2017-2021"}],
    }
    base.update(overrides)
    return ResumeTailorerOutput.model_validate(base)


def test_grounded_content_yields_no_warnings():
    assert validate_resume_faithfulness(_content(), _SOURCE) == []


def test_fabricated_employer_flagged():
    content = _content(experience=[{"company": "Google", "role": "SWE", "bullets": []}])
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_employer" in rules


def test_fabricated_institution_flagged():
    content = _content(education=[{"institution": "MIT", "degree": "BSc"}])
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_institution" in rules


def test_fabricated_skill_flagged_but_content_not_mutated():
    content = _content(skills=["Python", "Kubernetes"])
    warnings = validate_resume_faithfulness(content, _SOURCE)
    assert "unsupported_skill" in [w.rule for w in warnings]
    assert content.skills == ["Python", "Kubernetes"]  # NON-mutating: nothing stripped


def test_fabricated_metric_flagged():
    content = _content(
        experience=[
            {"company": "Acme Corp", "role": "SWE", "bullets": ["Improved throughput by 87%"]}
        ]
    )
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_metric" in rules


def test_supported_metric_not_flagged():
    content = _content(
        experience=[{"company": "Acme Corp", "role": "SWE", "bullets": ["Cut p99 latency by 40%"]}]
    )
    assert [
        w for w in validate_resume_faithfulness(content, _SOURCE) if w.rule == "unsupported_metric"
    ] == []


def test_dash_flagged_even_without_source():
    content = _content(summary="Engineer — loves Python")
    rules = [w.rule for w in validate_resume_faithfulness(content, None)]
    assert rules == ["style_dash"]  # dash check runs; grounding checks skipped (no source)


def test_empty_source_skips_grounding_checks():
    content = _content(skills=["Kubernetes"], experience=[{"company": "Google", "bullets": []}])
    assert validate_resume_faithfulness(content, "") == []


def test_all_warnings_are_warn_severity_from_resume_editor():
    content = _content(skills=["Kubernetes"], summary="dash — here")
    for w in validate_resume_faithfulness(content, _SOURCE):
        assert w.agent == "resume_editor" and w.severity == "warn"
