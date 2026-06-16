from __future__ import annotations

from backend.evals.dataset import DEFAULT_FIXTURE_PATH, load_eval_cases


def test_eval_dataset_loads_and_has_expected_case_count():
    cases = load_eval_cases()

    assert DEFAULT_FIXTURE_PATH.exists()
    assert len(cases) >= 5
    assert {case.case_id for case in cases} >= {
        "ai_software_engineer_startup",
        "applied_ai_engineer_healthtech",
        "backend_engineer_platform",
        "data_ml_engineer_analytics",
        "forward_deployed_engineer_ai",
    }


def test_eval_dataset_uses_synthetic_inputs_only():
    cases = load_eval_cases()

    for case in cases:
        joined = " ".join(
            [case.candidate_profile_text, case.resume_text, case.job_description]
        ).lower()
        assert "synthetic candidate" in joined
        assert "@gmail.com" not in joined
        assert "linkedin.com/in/" not in joined
