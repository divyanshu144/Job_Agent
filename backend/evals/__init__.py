"""Evals package (scaffold).

The original eval harness — `validators.py` with per-agent `validate_*` functions and a
`test_consistency` suite (match_scorer 3× variance ≤ 15) — existed locally but its source was
never committed and is unrecoverable (see tasks/observability-audit.md #8). This package is the
intended home for a reconstructed scorer.

EVALS HOOK (Wave 4 feedback track): a future scorer here should consume the `Feedback` rows
(backend.models.Feedback) captured by routes/feedback.py and correlate them with `PipelineEvent`
spans/failures (joined on trace_id / analysis_id) to produce per-agent quality scores. Capture
is built; the scorer is deliberately out of scope until reconstruction is scheduled.
"""
