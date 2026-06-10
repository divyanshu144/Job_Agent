# Session Handoff

**Updated:** 2026-06-10
**Branch:** main — BaseAgent self-correction shipped (commit pending)

---

## Current State

BaseAgent now self-corrects ONCE on `invalid_output`. `AgentError` + `_parse_json`
moved to `base.py` (re-exported from `job_parser.py` for back-compat).
`BaseAgent._call_structured(system, user, output_cls, *, label)` calls the model,
validates into `output_cls`, and on bad JSON / ValidationError / parse-AgentError
re-calls once with `_correction_prompt` (the validation error + `prior_raw[:500]`
fed back), logging a `PipelineEvent(kind="retry")`. Hard cap 2 calls; transient
errors (rate limit/timeout/connection) propagate untouched (SDK owns those).
Six agents migrated: job_parser, match_scorer, gap_analyst, cover_letter,
resume_tailorer, cold_email_agent. resource_planner excluded (bespoke multi-call
accounting) — zero lines changed. orchestrator.py — zero lines changed.

The earlier resume_tailorer omitted_items prompt bug is also fixed (commit
`9c79720`); self-correction is now the safety net for transient model slips.

## Next Action

No work in progress. Candidate follow-ups: surface `kind="retry"` self-correction
counts in the admin cost/telemetry dashboard, or extend bounded backoff config for
transient codes. Neither started.

## Why It Stopped

Task complete — self-correction loop implemented; `make check` green; constrained
files verified untouched.

## In-Flight

Uncommitted:
- backend/agents/base.py (AgentError/_parse_json + _call_structured/_correction_prompt/_log_retry)
- backend/agents/{job_parser,match_scorer,gap_analyst,cover_letter,resume_tailorer,cold_email_agent}.py
- tests/test_agents/test_base_self_correction.py (new), test_resume_tailorer.py, test_match_scorer.py
- tasks/agent_memory.md, tasks/lessons.md, HANDOFF.md

## Open Questions

None.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | ✓ 393 passed, 1 deselected · 80.15% coverage |
| `make lint` | ✓ clean (ruff + mypy + pydantic→TS drift) |
| `make check` | ✓ clean (run 2026-06-10) |
| orchestrator.py / resource_planner.py | ✓ zero lines changed (git diff empty) |
