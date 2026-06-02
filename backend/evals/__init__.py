"""Evals package.

Per-agent output validators live in `validators.py` (`validate_job_parser`,
`validate_match_scorer`, `validate_gap_analyst`, `validate_resource_planner`,
`validate_cover_letter`, `validate_resume_tailorer`); the consistency harness is
`scripts/consistency_check.py` with tests in `tests/test_evals/`.

EVALS HOOK (feedback track): a quality scorer here should consume the `Feedback` rows
(`backend.models.Feedback`) captured by `routes/feedback.py` and correlate them with
`PipelineEvent` spans/failures (joined on trace_id / analysis_id) to produce per-agent
quality scores — building on the existing `validate_*` functions. Feedback capture is built;
the scorer that consumes it is not yet implemented.
"""
