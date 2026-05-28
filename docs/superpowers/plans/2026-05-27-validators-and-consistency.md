# Validators + Consistency Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rule-based output validation to every pipeline agent (Part 1) and a real-API consistency test + CLI script for match_scorer (Part 2).

**Architecture:** Part 1 adds a pure-function `validate_X()` layer in `backend/evals/validators.py`; each agent's `run()` calls its validator after `model_validate()`, attaches warnings to the output object, and the orchestrator stores them automatically via `model_dump()`. Part 2 adds an `@pytest.mark.integration` test that calls the real Anthropic API and a `scripts/consistency_check.py` CLI; integration tests are excluded from `make test`.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, standard `logging`, `argparse` for the CLI script.

---

## Pre-flight: understand the call chain

Every agent follows this pattern (example: `job_parser.py`):

```python
async def run(self, profile: str, jd: str, prior: PriorOutputs) -> JobParserOutput:
    template = self._load_prompt("job_parser")
    system = self._inject(template, profile, jd, prior)
    raw = await self._call(system, jd)
    try:
        data = _parse_json(raw)
        return JobParserOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError, AgentError) as e:
        raise AgentError(f"job_parser: {e}") from e
```

After this task, the `return` line becomes:
```python
output = JobParserOutput.model_validate(data)
warnings = validate_job_parser(output, prior)
output.validation_warnings = warnings
return output
```

The orchestrator stores results via `output.model_dump()` — `validation_warnings` is a normal field so it's included automatically. No orchestrator changes needed.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| **Modify** | `backend/schemas.py` | Add `ValidationWarning` model; add `validation_warnings` field to all 6 output models |
| **Modify** | `frontend/src/types/index.ts` | Mirror `ValidationWarning` interface; add optional `validation_warnings` field to each output interface (required by `scripts/check_schema_drift.py`) |
| **Create** | `backend/evals/__init__.py` | Package marker (empty) |
| **Create** | `backend/evals/validators.py` | One `validate_X()` function per agent; all rules; logging |
| **Modify** | `backend/agents/job_parser.py` | Call `validate_job_parser()` after `model_validate` |
| **Modify** | `backend/agents/match_scorer.py` | Call `validate_match_scorer()` |
| **Modify** | `backend/agents/gap_analyst.py` | Call `validate_gap_analyst()` |
| **Modify** | `backend/agents/resource_planner.py` | Call `validate_resource_planner()` |
| **Modify** | `backend/agents/cover_letter.py` | Call `validate_cover_letter()` |
| **Modify** | `backend/agents/resume_tailorer.py` | Call `validate_resume_tailorer()` |
| **Create** | `tests/test_evals/__init__.py` | Package marker (empty) |
| **Create** | `tests/test_evals/test_validators.py` | One passing + one failing test per rule |
| **Modify** | `pyproject.toml` | Register `integration` pytest marker; add `-m "not integration"` to default addopts |
| **Modify** | `Makefile` | Add `eval-consistency` target |
| **Create** | `tests/test_evals/test_consistency.py` | @pytest.mark.integration test (calls real API) |
| **Create** | `scripts/consistency_check.py` | CLI: --jd-file --runs, exits 1 if variance > 15 |

---

## PART 1 — Inline Validators

---

### Task 1: Extend schemas.py

**Files:**
- Modify: `backend/schemas.py`
- Modify: `frontend/src/types/index.ts`

The drift checker (`scripts/check_schema_drift.py`) compares field names between Python classes and TypeScript interfaces. Adding `validation_warnings` to Python models requires adding it to TypeScript too.

- [ ] **Step 1: Add `ValidationWarning` and field to all output models in `backend/schemas.py`**

Add after the imports, before `GapItem`:

```python
from typing import Literal
```

Add after `GapItem`/`ResourceItem`/`BulletItem` definitions (before `JobParserOutput`):

```python
class ValidationWarning(BaseModel):
    agent: str
    rule: str
    detail: str
    severity: Literal["warn", "error"]
```

Then add `validation_warnings: list[ValidationWarning] = []` as the **last** field to each output model:

```python
class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str
    company: str | None = None
    validation_warnings: list[ValidationWarning] = []


class MatchScorerOutput(BaseModel):
    score: int = Field(..., ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    partial_matches: list[str]
    validation_warnings: list[ValidationWarning] = []


class GapAnalystOutput(BaseModel):
    critical_gaps: list[GapItem]
    nice_to_have_gaps: list[GapItem]
    validation_warnings: list[ValidationWarning] = []


class ResourcePlannerOutput(BaseModel):
    gaps: list[ResourceItem]
    validation_warnings: list[ValidationWarning] = []


class CoverLetterOutput(BaseModel):
    subject: str
    body: str
    tone_notes: str
    validation_warnings: list[ValidationWarning] = []


class ResumeTailorerOutput(BaseModel):
    tailored_bullets: list[BulletItem]
    validation_warnings: list[ValidationWarning] = []
```

- [ ] **Step 2: Mirror in `frontend/src/types/index.ts`**

Add before `ProfileResponse` interface:
```typescript
export interface ValidationWarning { agent: string; rule: string; detail: string; severity: 'warn' | 'error'; }
```

Add `validation_warnings?: ValidationWarning[];` as the last field to each of the 6 output interfaces. Example for `JobParserOutput`:
```typescript
export interface JobParserOutput { required_skills: string[]; nice_to_have: string[]; years_experience: number | null; role_type: string; seniority: string; company?: string | null; validation_warnings?: ValidationWarning[]; }
```

Do the same for `MatchScorerOutput`, `GapAnalystOutput`, `ResourcePlannerOutput`, `CoverLetterOutput`, `ResumeTailorerOutput`.

- [ ] **Step 3: Verify drift check passes**

```bash
python scripts/check_schema_drift.py
```

Expected: `Schema drift check passed (9 classes)`

---

### Task 2: Create `backend/evals/validators.py`

**Files:**
- Create: `backend/evals/__init__.py`
- Create: `backend/evals/validators.py`

- [ ] **Step 1: Create package marker**

```bash
touch backend/evals/__init__.py
```

- [ ] **Step 2: Write `backend/evals/validators.py`**

```python
from __future__ import annotations

import logging

from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
    ValidationWarning,
)

logger = logging.getLogger(__name__)

_VALID_SENIORITIES = {"Junior", "Mid", "Senior", "Lead", "Staff", "Principal"}


def _warn(agent: str, rule: str, detail: str, severity: str = "warn") -> ValidationWarning:
    w: ValidationWarning = ValidationWarning(agent=agent, rule=rule, detail=detail, severity=severity)  # type: ignore[arg-type]
    logger.warning("[%s] %s: %s", agent, rule, detail)
    return w


def validate_job_parser(output: JobParserOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if output.seniority not in _VALID_SENIORITIES:
        warnings.append(_warn(
            "job_parser", "invalid_seniority",
            f"seniority '{output.seniority}' not in {sorted(_VALID_SENIORITIES)}",
        ))
    if output.years_experience is not None and not (0 <= output.years_experience <= 30):
        warnings.append(_warn(
            "job_parser", "years_experience_out_of_range",
            f"years_experience={output.years_experience} not in [0, 30]",
        ))
    return warnings


def validate_match_scorer(output: MatchScorerOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    # Defensive score range check (Pydantic enforces this, but emit a warn too)
    if not (0 <= output.score <= 100):
        warnings.append(_warn(
            "match_scorer", "score_out_of_range",
            f"score={output.score} not in [0, 100]",
        ))
    overlap = set(output.matched_skills) & set(output.missing_skills)
    if overlap:
        warnings.append(_warn(
            "match_scorer", "skills_overlap",
            f"skills in both matched and missing: {sorted(overlap)}",
            severity="error",
        ))
    if output.score >= 85 and len(output.missing_skills) > 5:
        warnings.append(_warn(
            "match_scorer", "high_score_many_gaps",
            f"Score {output.score} but {len(output.missing_skills)} missing skills",
        ))
    return warnings


def validate_gap_analyst(output: GapAnalystOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if prior.match_scorer is not None:
        missing = {s.lower() for s in prior.match_scorer.missing_skills}
        for gap in output.critical_gaps:
            if gap.skill.lower() not in missing:
                warnings.append(_warn(
                    "gap_analyst", "critical_gap_not_in_missing_skills",
                    f"'{gap.skill}' in critical_gaps but not in match_scorer.missing_skills",
                    severity="error",
                ))
        if prior.match_scorer.missing_skills and not output.critical_gaps:
            warnings.append(_warn(
                "gap_analyst", "empty_critical_gaps",
                f"match_scorer reported {len(prior.match_scorer.missing_skills)} missing skills "
                f"but critical_gaps is empty",
            ))
    return warnings


def validate_resource_planner(
    output: ResourcePlannerOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    for gap in output.gaps:
        if not (1 <= gap.estimated_hours <= 500):
            warnings.append(_warn(
                "resource_planner", "hours_out_of_range",
                f"'{gap.skill}': estimated_hours={gap.estimated_hours} not in [1, 500]",
            ))
        if not gap.courses and not gap.books:
            warnings.append(_warn(
                "resource_planner", "no_resources",
                f"'{gap.skill}': no courses or books provided",
            ))
    return warnings


def validate_cover_letter(output: CoverLetterOutput, prior: PriorOutputs) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    word_count = len(output.body.split())
    if word_count < 150:
        warnings.append(_warn(
            "cover_letter", "body_too_short",
            f"body has {word_count} words, minimum is 150",
            severity="error",
        ))
    sentences = [s.strip() for s in output.body.split(". ") if s.strip()]
    if len(sentences) != len(set(sentences)):
        warnings.append(_warn(
            "cover_letter", "duplicate_sentences",
            "body contains at least one repeated sentence",
        ))
    if prior.job_parser is not None:
        required = {s.lower() for s in prior.job_parser.required_skills}
        body_lower = output.body.lower()
        if required and not any(skill in body_lower for skill in required):
            warnings.append(_warn(
                "cover_letter", "no_required_skills_mentioned",
                f"body does not mention any of the required skills: {prior.job_parser.required_skills}",
            ))
    return warnings


def validate_resume_tailorer(
    output: ResumeTailorerOutput, prior: PriorOutputs
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    if not output.tailored_bullets:
        warnings.append(_warn(
            "resume_tailorer", "no_bullets",
            "tailored_bullets is empty",
            severity="error",
        ))
    for bullet in output.tailored_bullets:
        orig_words = set(bullet.original.split())
        new_words = set(bullet.rewritten.split())
        union = orig_words | new_words
        if union:
            diff_ratio = len(new_words - orig_words) / len(union)
            if diff_ratio < 0.2:
                warnings.append(_warn(
                    "resume_tailorer", "bullet_too_similar",
                    f"rewritten differs from original by only {diff_ratio:.0%} "
                    f"(minimum 20%): '{bullet.original[:60]}'",
                ))
    return warnings
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from backend.evals.validators import validate_job_parser; print('ok')"
```

Expected: `ok`

---

### Task 3: Write failing validator tests

**Files:**
- Create: `tests/test_evals/__init__.py`
- Create: `tests/test_evals/test_validators.py`

Write all tests BEFORE wiring the validators into agents. Tests should fail right now because the agents don't call validators yet.

- [ ] **Step 1: Create package marker**

```bash
touch tests/test_evals/__init__.py
```

- [ ] **Step 2: Write `tests/test_evals/test_validators.py`**

```python
from __future__ import annotations

import pytest

from backend.evals.validators import (
    validate_cover_letter,
    validate_gap_analyst,
    validate_job_parser,
    validate_match_scorer,
    validate_resource_planner,
    validate_resume_tailorer,
)
from backend.schemas import (
    BulletItem,
    CoverLetterOutput,
    GapAnalystOutput,
    GapItem,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourceItem,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _jp(**kw) -> JobParserOutput:
    defaults = dict(required_skills=["Python"], nice_to_have=[], role_type="Engineer", seniority="Senior")
    return JobParserOutput(**(defaults | kw))


def _ms(**kw) -> MatchScorerOutput:
    defaults = dict(score=75, matched_skills=["Python"], missing_skills=["Docker"], partial_matches=[])
    return MatchScorerOutput(**(defaults | kw))


def _ga(**kw) -> GapAnalystOutput:
    defaults = dict(critical_gaps=[], nice_to_have_gaps=[])
    return GapAnalystOutput(**(defaults | kw))


def _rp(**kw) -> ResourcePlannerOutput:
    defaults = dict(gaps=[])
    return ResourcePlannerOutput(**(defaults | kw))


def _cl(**kw) -> CoverLetterOutput:
    long_body = "I am a software engineer. " * 20  # 100 words * 2 = 100 words of content, make it longer
    defaults = dict(subject="Cover Letter", body=long_body, tone_notes="professional")
    return CoverLetterOutput(**(defaults | kw))


def _rt(**kw) -> ResumeTailorerOutput:
    defaults = dict(tailored_bullets=[])
    return ResumeTailorerOutput(**(defaults | kw))


EMPTY_PRIOR = PriorOutputs()


# ---------------------------------------------------------------------------
# job_parser rules
# ---------------------------------------------------------------------------

def test_job_parser_valid_seniority_no_warning():
    out = _jp(seniority="Senior")
    warnings = validate_job_parser(out, EMPTY_PRIOR)
    assert not any(w.rule == "invalid_seniority" for w in warnings)


def test_job_parser_invalid_seniority_warns():
    out = _jp(seniority="Entry Level")
    warnings = validate_job_parser(out, EMPTY_PRIOR)
    assert any(w.rule == "invalid_seniority" and w.severity == "warn" for w in warnings)


def test_job_parser_years_experience_in_range_no_warning():
    out = _jp(years_experience=5)
    warnings = validate_job_parser(out, EMPTY_PRIOR)
    assert not any(w.rule == "years_experience_out_of_range" for w in warnings)


def test_job_parser_years_experience_none_no_warning():
    out = _jp(years_experience=None)
    warnings = validate_job_parser(out, EMPTY_PRIOR)
    assert not any(w.rule == "years_experience_out_of_range" for w in warnings)


def test_job_parser_years_experience_out_of_range_warns():
    out = _jp(years_experience=99)
    warnings = validate_job_parser(out, EMPTY_PRIOR)
    assert any(w.rule == "years_experience_out_of_range" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# match_scorer rules
# ---------------------------------------------------------------------------

def test_match_scorer_no_overlap_no_warning():
    out = _ms(matched_skills=["Python"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "skills_overlap" for w in warnings)


def test_match_scorer_overlap_is_error():
    out = _ms(matched_skills=["Python", "Docker"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert any(w.rule == "skills_overlap" and w.severity == "error" for w in warnings)


def test_match_scorer_high_score_few_gaps_no_warning():
    out = _ms(score=90, missing_skills=["A", "B"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "high_score_many_gaps" for w in warnings)


def test_match_scorer_high_score_many_gaps_warns():
    out = _ms(score=90, missing_skills=["A", "B", "C", "D", "E", "F"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    assert any(w.rule == "high_score_many_gaps" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# gap_analyst rules
# ---------------------------------------------------------------------------

def test_gap_analyst_critical_gap_in_missing_no_warning():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker"]))
    out = _ga(critical_gaps=[GapItem(skill="Docker", impact="high", rationale="required")])
    warnings = validate_gap_analyst(out, prior)
    assert not any(w.rule == "critical_gap_not_in_missing_skills" for w in warnings)


def test_gap_analyst_critical_gap_not_in_missing_is_error():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker"]))
    out = _ga(critical_gaps=[GapItem(skill="Kubernetes", impact="high", rationale="extra")])
    warnings = validate_gap_analyst(out, prior)
    assert any(w.rule == "critical_gap_not_in_missing_skills" and w.severity == "error" for w in warnings)


def test_gap_analyst_empty_critical_gaps_with_missing_warns():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=["Docker", "AWS"]))
    out = _ga(critical_gaps=[])
    warnings = validate_gap_analyst(out, prior)
    assert any(w.rule == "empty_critical_gaps" and w.severity == "warn" for w in warnings)


def test_gap_analyst_empty_gaps_no_missing_no_warning():
    prior = PriorOutputs(match_scorer=_ms(missing_skills=[]))
    out = _ga(critical_gaps=[])
    warnings = validate_gap_analyst(out, prior)
    assert not any(w.rule == "empty_critical_gaps" for w in warnings)


# ---------------------------------------------------------------------------
# resource_planner rules
# ---------------------------------------------------------------------------

def _gap_item(skill: str, hours: int, courses: list[str], books: list[str]) -> ResourceItem:
    return ResourceItem(skill=skill, courses=courses, books=books, projects=[], estimated_hours=hours)


def test_resource_planner_valid_hours_no_warning():
    out = _rp(gaps=[_gap_item("Docker", 10, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert not any(w.rule == "hours_out_of_range" for w in warnings)


def test_resource_planner_zero_hours_warns():
    out = _rp(gaps=[_gap_item("Docker", 0, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert any(w.rule == "hours_out_of_range" and w.severity == "warn" for w in warnings)


def test_resource_planner_has_resources_no_warning():
    out = _rp(gaps=[_gap_item("Docker", 10, ["Course A"], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_resources" for w in warnings)


def test_resource_planner_no_resources_warns():
    out = _rp(gaps=[_gap_item("Docker", 10, [], [])])
    warnings = validate_resource_planner(out, EMPTY_PRIOR)
    assert any(w.rule == "no_resources" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# cover_letter rules
# ---------------------------------------------------------------------------

_LONG_BODY = " ".join(["word"] * 160)  # 160 words — passes the 150-word check


def test_cover_letter_long_body_no_error():
    out = _cl(body=_LONG_BODY)
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert not any(w.rule == "body_too_short" for w in warnings)


def test_cover_letter_short_body_is_error():
    out = _cl(body="Too short.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert any(w.rule == "body_too_short" and w.severity == "error" for w in warnings)


def test_cover_letter_no_duplicate_sentences_no_warning():
    out = _cl(body="I am great. I have skills. I want the job.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert not any(w.rule == "duplicate_sentences" for w in warnings)


def test_cover_letter_duplicate_sentence_warns():
    out = _cl(body="I am great. I am great. I want the job.")
    warnings = validate_cover_letter(out, EMPTY_PRIOR)
    assert any(w.rule == "duplicate_sentences" and w.severity == "warn" for w in warnings)


def test_cover_letter_mentions_required_skill_no_warning():
    prior = PriorOutputs(job_parser=_jp(required_skills=["Python"]))
    out = _cl(body=_LONG_BODY + " Python experience included.")
    warnings = validate_cover_letter(out, prior)
    assert not any(w.rule == "no_required_skills_mentioned" for w in warnings)


def test_cover_letter_missing_required_skill_warns():
    prior = PriorOutputs(job_parser=_jp(required_skills=["Rust"]))
    out = _cl(body=_LONG_BODY)  # body doesn't mention Rust
    warnings = validate_cover_letter(out, prior)
    assert any(w.rule == "no_required_skills_mentioned" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# resume_tailorer rules
# ---------------------------------------------------------------------------

def test_resume_tailorer_non_empty_bullets_no_error():
    bullet = BulletItem(original="Built APIs", rewritten="Designed REST APIs using FastAPI", rationale="more specific")
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "no_bullets" for w in warnings)


def test_resume_tailorer_empty_bullets_is_error():
    out = _rt(tailored_bullets=[])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert any(w.rule == "no_bullets" and w.severity == "error" for w in warnings)


def test_resume_tailorer_significantly_different_bullet_no_warning():
    bullet = BulletItem(
        original="Built APIs",
        rewritten="Designed and implemented scalable REST services using FastAPI and PostgreSQL",
        rationale="added detail",
    )
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert not any(w.rule == "bullet_too_similar" for w in warnings)


def test_resume_tailorer_too_similar_bullet_warns():
    bullet = BulletItem(original="Built APIs", rewritten="Built APIs", rationale="unchanged")
    out = _rt(tailored_bullets=[bullet])
    warnings = validate_resume_tailorer(out, EMPTY_PRIOR)
    assert any(w.rule == "bullet_too_similar" and w.severity == "warn" for w in warnings)


# ---------------------------------------------------------------------------
# Cross-cutting: warnings attached to output, not raised
# ---------------------------------------------------------------------------

def test_warnings_do_not_raise_exceptions():
    """Validation failures must never raise — they produce ValidationWarning objects."""
    out = _jp(seniority="Entry Level", years_experience=99)
    try:
        warnings = validate_job_parser(out, EMPTY_PRIOR)
    except Exception as exc:
        pytest.fail(f"validate_job_parser raised an exception: {exc}")
    assert len(warnings) == 2


def test_error_severity_distinguishable_from_warn():
    out = _ms(matched_skills=["Docker"], missing_skills=["Docker"])
    warnings = validate_match_scorer(out, EMPTY_PRIOR)
    errors = [w for w in warnings if w.severity == "error"]
    warns = [w for w in warnings if w.severity == "warn"]
    assert errors  # at least one error
    # errors and warns are structurally the same type, just different severity value
    assert all(hasattr(w, "severity") for w in errors + warns)
```

- [ ] **Step 3: Run tests — expect RED**

```bash
pytest tests/test_evals/test_validators.py -v 2>&1 | tail -20
```

Expected: tests fail because the validator functions have known logic (they should actually pass here since we're testing the validators directly, NOT agent integration). 

Actually these tests test `validate_X()` functions directly, not the agent's `run()`. Since the validators already exist (from Task 2), these tests should go **GREEN** immediately. That's correct TDD here: the validator functions are the unit under test, and Task 3 tests them in isolation.

Run and confirm all pass:

```bash
pytest tests/test_evals/test_validators.py -v
```

Expected: all pass (validators are pure functions, no agent integration needed).

---

### Task 4: Wire validators into each agent's `run()`

This is the integration step. We modify each agent so validation runs automatically after parsing.

- [ ] **Step 1: Update `backend/agents/job_parser.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import HAIKU, BaseAgent
from backend.evals.validators import validate_job_parser
from backend.schemas import JobParserOutput, PriorOutputs


class AgentError(Exception):
    pass


def _parse_json(raw: str) -> dict[str, object]:
    """Extract and parse the first JSON object from a string."""
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise AgentError(f"No JSON object found in response: {raw[:100]}")
    result: dict[str, object] = json.loads(raw[start:end])
    return result


class JobParserAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> JobParserOutput:
        template = self._load_prompt("job_parser")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            data = _parse_json(raw)
            output = JobParserOutput.model_validate(data)
            output.validation_warnings = validate_job_parser(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"job_parser: {e}") from e
```

- [ ] **Step 2: Update `backend/agents/match_scorer.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import HAIKU, BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_match_scorer
from backend.schemas import MatchScorerOutput, PriorOutputs


class MatchScorerAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> MatchScorerOutput:
        template = self._load_prompt("match_scorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = MatchScorerOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_match_scorer(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"match_scorer: {e}") from e
```

- [ ] **Step 3: Update `backend/agents/gap_analyst.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_gap_analyst
from backend.schemas import GapAnalystOutput, PriorOutputs


class GapAnalystAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> GapAnalystOutput:
        template = self._load_prompt("gap_analyst")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = GapAnalystOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_gap_analyst(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"gap_analyst: {e}") from e
```

- [ ] **Step 4: Update `backend/agents/resource_planner.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_resource_planner
from backend.schemas import PriorOutputs, ResourcePlannerOutput


class ResourcePlannerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResourcePlannerOutput:
        template = self._load_prompt("resource_planner")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = ResourcePlannerOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_resource_planner(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resource_planner: {e}") from e
```

- [ ] **Step 5: Update `backend/agents/cover_letter.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_cover_letter
from backend.schemas import CoverLetterOutput, PriorOutputs


class CoverLetterAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> CoverLetterOutput:
        template = self._load_prompt("cover_letter")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = CoverLetterOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_cover_letter(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cover_letter: {e}") from e
```

- [ ] **Step 6: Update `backend/agents/resume_tailorer.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_resume_tailorer
from backend.schemas import PriorOutputs, ResumeTailorerOutput


class ResumeTailorerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResumeTailorerOutput:
        template = self._load_prompt("resume_tailorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            output = ResumeTailorerOutput.model_validate(_parse_json(raw))
            output.validation_warnings = validate_resume_tailorer(output, prior)
            return output
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resume_tailorer: {e}") from e
```

- [ ] **Step 7: Run `make check` — expect GREEN**

```bash
make check
```

Expected: all 134+ tests pass, lint clean, mypy clean.

Watch for: existing agent tests mock `_call()` and return raw JSON strings — they don't call `validate_X()` because they mock at `_call` level. The validators are exercised by `tests/test_evals/test_validators.py` directly.

---

## PART 2 — Consistency Testing

---

### Task 5: Configure pytest markers + Makefile

- [ ] **Step 1: Add `integration` marker to `pyproject.toml`**

Add the markers section and update `addopts` to exclude integration tests from the default run:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=backend --cov-report=term-missing --cov-fail-under=70 -m 'not integration'"
markers = [
    "integration: marks tests that call external APIs (deselect with '-m not integration')",
]
```

- [ ] **Step 2: Add `eval-consistency` target to `Makefile`**

```makefile
eval-consistency:
	pytest tests/test_evals/test_consistency.py -v -m integration
```

The full updated Makefile:

```makefile
.PHONY: run test fmt lint check docker-up eval-consistency

run:
	uvicorn backend.main:app --reload --port 8000 & cd frontend && npm run dev

test:
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-fail-under=70 -m "not integration"

fmt:
	ruff format backend/ tests/

lint:
	ruff check backend/ tests/
	mypy backend/
	python scripts/check_schema_drift.py

check:
	make fmt && make lint && make test

eval-consistency:
	pytest tests/test_evals/test_consistency.py -v -m integration

docker-up:
	docker-compose up --build
```

---

### Task 6: Write the consistency test

**Files:**
- Create: `tests/test_evals/test_consistency.py`

- [ ] **Step 1: Write `tests/test_evals/test_consistency.py`**

```python
from __future__ import annotations

"""
Integration test: run match_scorer N times on the same input and assert
score variance and skill overlap are within acceptable bounds.

Run with:  make eval-consistency
Skip in:   make test   (filtered by -m 'not integration')
"""

import pytest

from backend.agents.match_scorer import MatchScorerAgent
from backend.schemas import MatchScorerOutput, PriorOutputs

# ---------------------------------------------------------------------------
# Fixed fixtures — realistic 200-word SWE job description
# ---------------------------------------------------------------------------

JD = """
We are looking for a Senior Backend Engineer to join our platform team.
You will design, build, and maintain high-performance APIs and services that
power our core product. The role requires deep expertise in Python and
experience with distributed systems.

Responsibilities:
- Design and implement RESTful APIs using FastAPI or Django REST Framework
- Build and operate services on AWS (ECS, RDS, S3, SQS)
- Work with PostgreSQL and Redis for persistence and caching
- Contribute to CI/CD pipelines using GitHub Actions and Docker
- Collaborate with frontend engineers and product managers
- Participate in on-call rotation and incident response

Requirements:
- 4+ years of backend engineering experience
- Strong Python skills (asyncio, type hints, testing with pytest)
- Experience with SQL databases and query optimisation
- Familiarity with containerisation (Docker, Kubernetes)
- Comfortable with system design and API design patterns
- Experience with message queues (SQS, RabbitMQ, or Kafka) is a plus

We value clear communication, ownership, and iterative delivery.
Remote-friendly within EU time zones.
""".strip()

PROFILE = """
Software engineer, 5 years experience.
Skills: Python, FastAPI, PostgreSQL, Docker, AWS, Redis, pytest, GitHub Actions.
""".strip()


def _jaccard_overlap(a: list[str], b: list[str]) -> float:
    """Fraction of items in the union that appear in both lists (case-insensitive)."""
    sa = {s.lower() for s in a}
    sb = {s.lower() for s in b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


@pytest.mark.integration
async def test_match_scorer_consistency():
    """
    Run match_scorer 3 times on identical input.
    Assert:
      - All runs return valid MatchScorerOutput
      - Score variance (max - min) <= 15
      - matched_skills pairwise Jaccard overlap >= 0.70
      - missing_skills pairwise Jaccard overlap >= 0.70
    """
    agent = MatchScorerAgent()
    prior = PriorOutputs()
    runs: list[MatchScorerOutput] = []

    for i in range(3):
        result = await agent.run(PROFILE, JD, prior)
        assert isinstance(result, MatchScorerOutput), f"Run {i+1}: expected MatchScorerOutput"
        assert 0 <= result.score <= 100, f"Run {i+1}: score {result.score} out of range"
        runs.append(result)

    scores = [r.score for r in runs]
    variance = max(scores) - min(scores)

    # Pairwise skill overlaps
    matched_overlaps = [
        _jaccard_overlap(runs[i].matched_skills, runs[j].matched_skills)
        for i in range(3) for j in range(i + 1, 3)
    ]
    missing_overlaps = [
        _jaccard_overlap(runs[i].missing_skills, runs[j].missing_skills)
        for i in range(3) for j in range(i + 1, 3)
    ]
    avg_matched = sum(matched_overlaps) / len(matched_overlaps) if matched_overlaps else 1.0
    avg_missing = sum(missing_overlaps) / len(missing_overlaps) if missing_overlaps else 1.0

    # ---- Report ----
    print("\n=== match_scorer consistency report ===")
    for i, r in enumerate(runs, 1):
        print(f"  Run {i}: score={r.score}  matched={r.matched_skills}  missing={r.missing_skills}")
    print(f"  Score variance:       {variance}  (threshold ≤ 15)")
    print(f"  matched_skills overlap: {avg_matched:.0%}  (threshold ≥ 70%)")
    print(f"  missing_skills overlap: {avg_missing:.0%}  (threshold ≥ 70%)")

    # ---- Assertions ----
    assert variance <= 15, (
        f"Score variance too high: {scores} → variance={variance} (max 15)"
    )
    assert avg_matched >= 0.70, (
        f"matched_skills overlap too low: {avg_matched:.0%} (min 70%)"
    )
    assert avg_missing >= 0.70, (
        f"missing_skills overlap too low: {avg_missing:.0%} (min 70%)"
    )
```

- [ ] **Step 2: Verify test is excluded from normal run**

```bash
make test
```

Expected: `test_consistency.py` not collected. Same count as before Part 2.

---

### Task 7: Write `scripts/consistency_check.py`

**Files:**
- Create: `scripts/consistency_check.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Standalone consistency checker for match_scorer.

Usage:
    python scripts/consistency_check.py --jd-file path/to/jd.txt
    python scripts/consistency_check.py --jd-file path/to/jd.txt --runs 5

Exit codes:
    0  — variance within threshold (≤ 15)
    1  — variance exceeds threshold
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _jaccard_overlap(a: list[str], b: list[str]) -> float:
    sa = {s.lower() for s in a}
    sb = {s.lower() for s in b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


async def _run(jd: str, runs: int) -> int:
    from backend.agents.match_scorer import MatchScorerAgent
    from backend.schemas import MatchScorerOutput, PriorOutputs

    agent = MatchScorerAgent()
    prior = PriorOutputs()
    results: list[MatchScorerOutput] = []

    print(f"Running match_scorer {runs} time(s)…")
    for i in range(runs):
        out = await agent.run("", jd, prior)
        results.append(out)
        print(f"  Run {i + 1}: score={out.score}")

    scores = [r.score for r in results]
    variance = max(scores) - min(scores) if len(scores) > 1 else 0

    pairs = [(i, j) for i in range(runs) for j in range(i + 1, runs)]
    matched_overlaps = [_jaccard_overlap(results[i].matched_skills, results[j].matched_skills) for i, j in pairs]
    missing_overlaps = [_jaccard_overlap(results[i].missing_skills, results[j].missing_skills) for i, j in pairs]
    avg_matched = sum(matched_overlaps) / len(matched_overlaps) if matched_overlaps else 1.0
    avg_missing = sum(missing_overlaps) / len(missing_overlaps) if missing_overlaps else 1.0

    print("\n=== Consistency Report ===")
    print(f"  Scores:               {scores}")
    print(f"  Variance (max-min):   {variance}  {'✓' if variance <= 15 else '✗ EXCEEDS threshold of 15'}")
    print(f"  matched_skills overlap: {avg_matched:.0%}  {'✓' if avg_matched >= 0.70 else '✗'}")
    print(f"  missing_skills overlap: {avg_missing:.0%}  {'✓' if avg_missing >= 0.70 else '✗'}")

    return 0 if variance <= 15 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Check match_scorer consistency across N runs.")
    parser.add_argument("--jd-file", required=True, help="Path to a plain-text job description file")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs (default: 3)")
    args = parser.parse_args()

    jd = Path(args.jd_file).read_text()
    exit_code = asyncio.run(_run(jd, args.runs))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run `make check` — confirm green**

```bash
make check
```

Expected: all tests pass (integration test excluded), lint clean, mypy clean.

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| `ValidationWarning` model in schemas.py | Task 1 |
| `validation_warnings` field on all 6 output models | Task 1 |
| TS mirror for drift checker | Task 1 |
| `backend/evals/validators.py` with one function per agent | Task 2 |
| All rules per agent (seniority, years_exp, overlap, high_score_gaps, etc.) | Task 2 |
| Logging per warning | Task 2 |
| Call validator after model_validate in each agent | Task 4 |
| Warnings stored in JobResult.output_json (via model_dump) | Task 4 (automatic) |
| `tests/test_evals/test_validators.py` one test per rule, pass+fail | Task 3 |
| `@pytest.mark.integration` excluded from make test | Task 5 |
| `eval-consistency` Makefile target | Task 5 |
| Consistency test with fixed JD, 3 runs, variance ≤ 15, overlap ≥ 70% | Task 6 |
| Consistency report print | Task 6 |
| `scripts/consistency_check.py` CLI with --jd-file --runs | Task 7 |
| Script exits 1 if variance > 15 | Task 7 |

### Type consistency check

- `ValidationWarning` defined in Task 1, imported in Task 2 ✓
- `validate_X()` returns `list[ValidationWarning]`, assigned to `output.validation_warnings` in Task 4 ✓
- `_warn()` helper uses correct field names matching `ValidationWarning` ✓
- `Literal["warn", "error"]` used consistently in both Python and TS ✓
- `_jaccard_overlap` defined separately in both test and script (no shared import) ✓

### Placeholder check

No TBDs, no "similar to above", all code blocks complete ✓
