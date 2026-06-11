# AI Reliability

## BaseAgent Abstraction

`BaseAgent` in `backend/agents/base.py` is the shared boundary around Anthropic calls.

It provides:

- prompt loading from `backend/prompts/*.md`,
- template injection for profile, job description, and prior outputs,
- Anthropic client construction,
- LLM call tracking through `tracked_call()`,
- JSON parsing,
- Pydantic validation,
- one correction retry for malformed output.

Every pipeline agent subclasses `BaseAgent`:

- `JobParserAgent`
- `MatchScorerAgent`
- `GapAnalystAgent`
- `ResourcePlannerAgent`
- `CoverLetterAgent`
- `ResumeTailorerAgent`
- `ColdEmailAgent`

Why this matters: LLM calls are treated as unreliable external API calls. The shared base class centralizes validation, telemetry, and retry behavior.

## Pydantic Output Contracts

Output contracts live in `backend/schemas.py`.

Examples:

- `JobParserOutput`
- `MatchScorerOutput`
- `GapAnalystOutput`
- `ResourcePlannerOutput`
- `CoverLetterOutput`
- `ResumeTailorerOutput`
- `ColdEmailOutput`

These schemas convert free-form LLM text into typed application data. The orchestrator never treats raw model text as trusted output.

The frontend mirrors these types in `frontend/src/types/index.ts`. The script `scripts/check_schema_drift.py` checks selected backend/frontend schema pairs.

Current gap: the schema drift check covers important agent outputs, but not every API schema.

## JSON Correction Retry

`BaseAgent._call_structured()` performs the reliability loop:

1. Call Anthropic.
2. Extract the first JSON object.
3. Validate against the expected Pydantic model.
4. If parsing/validation fails, log a retry event.
5. Send a correction prompt containing the validation error and prior raw response.
6. Validate the second response.
7. If it still fails, raise `AgentError`.

This is intentionally capped at one retry. The system avoids unbounded retry loops that could silently burn cost.

## Failure Handling

The orchestrator catches agent exceptions in `backend/services/orchestrator.py`.

Failures are passed through `to_user_error()` in `backend/services/pipeline_errors.py`, which maps errors into user-safe categories:

- `invalid_output`
- `agent_failed`
- `rate_limited`
- `upstream_timeout`

Raw exception messages are logged, but user-facing messages do not include internal details.

On failure:

- the pipeline can continue when possible,
- successful steps are persisted,
- failed steps get a `JobResult.error` and `error_code`,
- the `Analysis` is marked `partial`,
- the UI can retry failed/missing steps.

## Resume Hallucination Guard

Resume hallucination checks live in `backend/evals/validators.py`, especially `validate_resume_tailorer()`.

Current safeguards:

- unsupported skills are removed if not found in CV text,
- unsupported employers are removed,
- unsupported degrees are removed,
- omitted items are recorded in `ResumeTailorerOutput.omitted_items`,
- bullets that mention known skills absent from CV text produce warnings.

This is a pragmatic guardrail. It does not prove every generated claim is true, but it reduces the most obvious unsupported resume claims.

## Current Eval Gaps

Existing eval-related code:

- Validators: `backend/evals/validators.py`
- Tests: `tests/test_evals/test_validators.py`
- Consistency tooling: `scripts/consistency_check.py`
- Integration marker in `pyproject.toml`

Gaps:

- No broad golden dataset of profile/JD pairs.
- No score-band regression suite for `match_scorer`.
- No automated cover-letter quality rubric beyond validators.
- No systematic hallucination/provenance scoring for generated resumes.
- No production feedback loop from `Feedback` rows into eval reports yet.

Recommended next step: create a small versioned eval dataset with expected score ranges, required extracted skills, forbidden unsupported claims, and minimum output completeness checks.
