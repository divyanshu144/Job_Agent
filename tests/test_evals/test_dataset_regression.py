from __future__ import annotations

import json

from backend.evals.runner import run_deterministic_eval
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    ResumeTailorerOutput,
)


def test_deterministic_eval_dataset_passes(tmp_path):
    report = tmp_path / "latest.json"

    result = run_deterministic_eval(report_path=report)

    assert result.passed is True
    assert result.failed_cases == 0
    assert report.exists()
    payload = json.loads(report.read_text())
    assert payload["passed"] is True
    assert payload["total_cases"] == result.total_cases
    assert payload["prompt_versions"]
    assert {item["agent_name"] for item in payload["prompt_versions"]} >= {
        "job_parser",
        "match_scorer",
        "gap_analyst",
        "cover_letter",
        "resume_tailorer",
    }


def test_mocked_outputs_satisfy_agent_output_schemas():
    from backend.evals.dataset import load_eval_cases

    for case in load_eval_cases():
        JobParserOutput.model_validate(case.mocked_outputs.job_parser)
        MatchScorerOutput.model_validate(case.mocked_outputs.match_scorer)
        GapAnalystOutput.model_validate(case.mocked_outputs.gap_analyst)
        CoverLetterOutput.model_validate(case.mocked_outputs.cover_letter)
        ResumeTailorerOutput.model_validate(case.mocked_outputs.resume_tailorer)


def test_regression_reports_property_failures(tmp_path):
    from backend.evals.dataset import load_eval_cases
    from backend.evals.runner import evaluate_case

    case = load_eval_cases()[0].model_copy(deep=True)
    case.mocked_outputs.match_scorer["score"] = 5

    result = evaluate_case(case)

    assert result.passed is False
    assert any("match_scorer.score" in failure for failure in result.failures)
