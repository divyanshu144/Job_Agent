# AI Evaluation Harness

JobFit Agent has a first deterministic AI eval harness for checking the main
agent workflow without calling Anthropic.

## What It Tests

The deterministic harness validates synthetic fixture cases against the existing
agent output schemas and quality validators:

- `JobParserOutput` extracts expected role, company, seniority, and required skills.
- `MatchScorerOutput` keeps scores inside case-specific ranges.
- `GapAnalystOutput` mentions expected missing skills.
- `CoverLetterOutput` mentions relevant skills and avoids forbidden unsupported claims.
- `ResumeTailorerOutput` satisfies minimum completeness rules and avoids forbidden unsupported claims.
- Existing validators in `backend/evals/validators.py` surface warnings for weak or unsupported outputs.

The checks are property based. They intentionally avoid exact prose snapshots
because generated wording is expected to vary.

## Fixture Location

Fixtures live in:

```text
tests/fixtures/evals/jobfit_eval_cases.json
```

Each case contains:

- `case_id`
- `job_description`
- `candidate_profile_text`
- `resume_text`
- `expected`
- `mocked_outputs`

All fixture data is synthetic. Do not add real resumes, real addresses, personal
emails, or private candidate details.

## How To Add A Case

1. Add a new object to `tests/fixtures/evals/jobfit_eval_cases.json`.
2. Use synthetic candidate/profile/resume text.
3. Fill `expected` with property checks:
   - `title_keywords`
   - `company`
   - `seniority`
   - `required_skills`
   - `score_min` / `score_max`
   - `relevant_skills`
   - `missing_skills`
   - `forbidden_unsupported_claims`
   - `completeness`
4. Add `mocked_outputs` that satisfy the existing Pydantic schemas in `backend/schemas.py`.
5. Run `make eval-deterministic`.

## Running Evals

Deterministic evals:

```bash
make eval-deterministic
```

Equivalent direct command:

```bash
python scripts/run_evals.py
```

The runner writes an ignored report to:

```text
reports/evals/latest.json
```

The report includes `prompt_versions` for the main pipeline prompts. Each entry
contains:

- `agent_name`
- `model`
- `prompt_name`
- `prompt_path`
- `prompt_hash`
- `prompt_version`

`prompt_hash` is a SHA-256 hash of the raw prompt template under
`backend/prompts/` before candidate profile, job description, or prior outputs
are injected. `prompt_version` is a short display version in the form
`sha256:<first-12-hex-chars>`.

Pytest coverage for the harness:

```bash
python -m pytest tests/test_evals -q
```

## Live Evals

Live evals are intentionally guarded. Default tests do not call Anthropic and do
not require API keys.

```bash
python scripts/run_evals.py --live
```

Without `RUN_LIVE_EVALS=1`, the live command exits successfully with a skip
message. With `RUN_LIVE_EVALS=1`, the command currently reports that live evals
are not implemented yet and exits successfully without making Anthropic calls.

## Current Limitations

- The dataset is small: five synthetic cases.
- The harness evaluates fixture-based mocked outputs, not real model outputs.
- No LLM-as-judge rubric is implemented.
- Prompt/model versions are recorded for deterministic reports and new
  `LLMCall` rows, but historical rows before this change have null prompt
  metadata.
- Validation warnings are surfaced in reports, but not persisted to the database.
- Discovery Stage 2 still manually extracts JSON in `backend/services/discovery.py`
  and `backend/services/batch_processor.py` is resolved: both paths now use the
  shared `Stage2Result` Pydantic contract and parser in `backend/services/stage2.py`.
- No database-backed eval run model exists yet.

## Follow-Up Tickets

1. Add deterministic discovery eval fixtures around `Stage2Result`.
2. Add optional live eval execution over the same fixture dataset.
3. Add cost and latency budgets for live evals.
4. Export a Markdown summary report for portfolio/interview review.
