# Pipeline Optimisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut per-analysis token cost and give users an explicit Evaluate → Generate workflow by tiering models, compressing profile context, and splitting the 6-agent pipeline into two user-triggered phases.

**Architecture:** Phase 1 (Evaluate) runs job_parser + match_scorer + gap_analyst using Haiku for the two parsing agents and a compact profile instead of the full merged profile. Phase 2 (Generate) runs resource_planner + cover_letter + resume_tailorer on demand via a new SSE endpoint, using the full profile. Both phases stream SSE events in the same format; the frontend shows a "Generate Documents" button between phases.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.0 async · Anthropic SDK (claude-haiku-4-5-20251001 + claude-sonnet-4-6) · React 18 · TypeScript · Tailwind CSS

---

## File Map

| File | Change |
|------|--------|
| `backend/agents/base.py` | Replace single `MODEL` constant with `HAIKU`/`SONNET`; make `_call` use `self.model` |
| `backend/agents/job_parser.py` | Add `model = HAIKU` |
| `backend/agents/match_scorer.py` | Add `model = HAIKU` |
| `backend/services/profile_builder.py` | Add `build_compact_profile()` |
| `backend/models.py` | Add `evaluate_only: bool` to `Analysis` |
| `backend/schemas.py` | Add `evaluate_only` to `AnalysisSummary`, `AnalysisDetail`, `PipelineDoneData` |
| `scripts/migrate.py` | Add step for `evaluate_only` column |
| `backend/routes/history.py` | Pass `evaluate_only` in `AnalysisDetail` constructor |
| `backend/services/orchestrator.py` | Replace `run_pipeline` with `run_evaluate_pipeline` + `run_generate_pipeline` |
| `backend/routes/analyse.py` | Update to `run_evaluate_pipeline`; add `POST /analyse/generate/{id}` |
| `tests/test_orchestrator/test_sse_sequence.py` | Update to new pipeline shape |
| `frontend/src/types/index.ts` | Add `evaluate_only`, `PHASE1_AGENTS`, `PHASE2_AGENTS` |
| `frontend/src/api/client.ts` | Extract SSE helper; add `streamGenerate` |
| `frontend/src/pages/AnalyseJob.tsx` | Evaluate → Generate two-phase UI |
| `frontend/src/pages/Results.tsx` | Show Generate button when `evaluate_only=true` |

---

## Task 1: Model tiering — base.py + job_parser + match_scorer

**Files:**
- Modify: `backend/agents/base.py`
- Modify: `backend/agents/job_parser.py`
- Modify: `backend/agents/match_scorer.py`
- Test: `tests/test_agents/test_model_tiering.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents/test_model_tiering.py
from backend.agents.base import HAIKU, SONNET
from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent


def test_haiku_agents():
    assert JobParserAgent().model == HAIKU
    assert MatchScorerAgent().model == HAIKU


def test_sonnet_agents():
    assert GapAnalystAgent().model == SONNET
    assert ResourcePlannerAgent().model == SONNET
    assert CoverLetterAgent().model == SONNET
    assert ResumeTailorerAgent().model == SONNET
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_agents/test_model_tiering.py -v
```
Expected: `FAILED — cannot import name 'HAIKU'`

- [ ] **Step 3: Replace base.py**

```python
# backend/agents/base.py
from __future__ import annotations

import json
from pathlib import Path

import anthropic

from backend.config import settings
from backend.schemas import PriorOutputs

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096


class BaseAgent:
    model: str = SONNET

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def _load_prompt(self, name: str) -> str:
        return (PROMPTS_DIR / f"{name}.md").read_text()

    def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs) -> str:
        result = template.replace("{profile}", profile).replace("{jd}", jd)
        for field, value in prior.model_dump(exclude_none=True).items():
            result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
        return result

    async def _call(self, system: str, user: str) -> str:
        msg = await self._client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
```

- [ ] **Step 4: Add `model = HAIKU` to job_parser.py**

In `backend/agents/job_parser.py`, change the import line and add the class attribute:

```python
from backend.agents.base import BaseAgent, HAIKU
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
            return JobParserOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"job_parser: {e}") from e
```

Full file (preserve the existing `import json` and `from pydantic import ValidationError`):

```python
# backend/agents/job_parser.py
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent, HAIKU
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
            return JobParserOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"job_parser: {e}") from e
```

- [ ] **Step 5: Add `model = HAIKU` to match_scorer.py**

```python
# backend/agents/match_scorer.py
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent, HAIKU
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import MatchScorerOutput, PriorOutputs


class MatchScorerAgent(BaseAgent):
    model = HAIKU

    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> MatchScorerOutput:
        template = self._load_prompt("match_scorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return MatchScorerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"match_scorer: {e}") from e
```

- [ ] **Step 6: Run tests to verify pass**

```bash
pytest tests/test_agents/test_model_tiering.py -v
```
Expected: `2 passed`

---

## Task 2: Compact profile extraction

**Files:**
- Modify: `backend/services/profile_builder.py`
- Test: `tests/test_services/test_compact_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_compact_profile.py
from backend.services.profile_builder import build_compact_profile


def test_includes_yaml_and_cv():
    result = build_compact_profile("name: Alice\nskills: [Python]", "Five years of ML engineering.")
    assert "name: Alice" in result
    assert "Five years" in result


def test_truncates_cv_at_500_chars():
    long_cv = "x" * 1000
    result = build_compact_profile("name: Alice", long_cv)
    assert result.count("x") == 500


def test_does_not_include_github_readmes():
    result = build_compact_profile("name: Alice", "cv text")
    # The full merged_profile would contain "## GitHub: owner/repo"
    # The compact version must not — it has no github data at all
    assert "## GitHub:" not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_services/test_compact_profile.py -v
```
Expected: `FAILED — cannot import name 'build_compact_profile'`

- [ ] **Step 3: Add function to profile_builder.py**

Add this function after `_assemble_merged` in `backend/services/profile_builder.py`:

```python
def build_compact_profile(yaml_text: str, cv_text: str) -> str:
    """Compact profile for early-stage agents (job_parser, match_scorer).

    Contains only YAML + first 500 chars of CV. Omits GitHub READMEs,
    which are large and not needed for parsing/scoring.
    """
    parts = ["## Candidate Profile (YAML)\n" + yaml_text]
    if cv_text.strip():
        parts.append("## CV Summary\n" + cv_text[:500])
    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/test_services/test_compact_profile.py -v
```
Expected: `3 passed`

---

## Task 3: DB schema — add evaluate_only to Analysis

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/schemas.py`
- Modify: `scripts/migrate.py`
- Modify: `backend/routes/history.py`
- Test: no new test file — existing DB/schema tests cover this

- [ ] **Step 1: Add field to Analysis model**

In `backend/models.py`, add `evaluate_only` to the `Analysis` class after `partial`:

```python
class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluate_only: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")
```

- [ ] **Step 2: Add migration step to scripts/migrate.py**

Add this block after the existing step 2 in `scripts/migrate.py`:

```python
    # 3. Add evaluate_only to analyses (DEFAULT 0 = complete, so existing rows are unaffected)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN evaluate_only BOOLEAN NOT NULL DEFAULT 0")
        print("✓ Added evaluate_only to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- evaluate_only already exists, skipping")
        else:
            raise
```

- [ ] **Step 3: Update schemas.py**

Replace the `AnalysisSummary` and `AnalysisDetail` classes, and add `PipelineDoneData`:

```python
class PipelineDoneData(BaseModel):
    analysis_id: str
    score: int
    partial: bool
    evaluate_only: bool


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool


class AnalysisDetail(BaseModel):
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    results: dict[str, dict]  # type: ignore[type-arg]
```

- [ ] **Step 4: Update history.py — pass evaluate_only to AnalysisDetail**

In `backend/routes/history.py`, update the `AnalysisDetail(...)` constructor call:

```python
    return AnalysisDetail(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        evaluate_only=analysis.evaluate_only,
        results=results_map,
    )
```

- [ ] **Step 5: Run migration**

```bash
python scripts/migrate.py
```
Expected output includes: `✓ Added evaluate_only to analyses`

- [ ] **Step 6: Run existing schema + DB tests to confirm no regressions**

```bash
pytest tests/test_schemas.py tests/test_database.py -v
```
Expected: all pass

---

## Task 4: Split orchestrator into evaluate + generate pipelines

**Files:**
- Modify: `backend/services/orchestrator.py`
- Modify: `tests/test_orchestrator/test_sse_sequence.py`

- [ ] **Step 1: Update the existing SSE test to match the new evaluate pipeline shape**

Replace `tests/test_orchestrator/test_sse_sequence.py` entirely:

```python
# tests/test_orchestrator/test_sse_sequence.py
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    ResourcePlannerOutput,
    ResumeTailorerOutput,
)
from datetime import datetime, timezone
import json

JD = "Senior ML Engineer role requiring Python, PyTorch, AWS experience. " * 5


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def stub_agents():
    jp = JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    )
    ms = MatchScorerOutput(score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="Cover Letter", body="Dear...", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])
    return jp, ms, ga, rp, cl, rt


async def test_evaluate_pipeline_sse_sequence(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    mock_profile = Profile(
        id="test-profile-id",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )

    with (
        patch(
            "backend.services.orchestrator.get_or_build_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ),
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline

        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    names = [e.name for e in events]
    assert names[0] == "pipeline_start"
    assert events[0].data["total_agents"] == 3
    assert names.count("agent_start") == 3
    assert names.count("agent_done") == 3
    assert names[-1] == "pipeline_done"

    starts = [e for e in events if e.name == "agent_start"]
    assert starts[0].data["agent"] == "job_parser"
    assert starts[1].data["agent"] == "match_scorer"
    assert starts[2].data["agent"] == "gap_analyst"

    done = events[-1]
    assert "analysis_id" in done.data
    assert done.data["score"] == 82
    assert done.data["partial"] is False
    assert done.data["evaluate_only"] is True


async def test_generate_pipeline_sse_sequence(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    # Seed a Phase 1 analysis with its results
    profile = Profile(
        id="test-profile-id",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile text",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    analysis = Analysis(
        jd_text=JD,
        profile_id=profile.id,
        partial=False,
        evaluate_only=True,
    )
    session.add(analysis)
    await session.flush()

    for name, output in [
        ("job_parser", jp.model_dump()),
        ("match_scorer", ms.model_dump()),
        ("gap_analyst", ga.model_dump()),
    ]:
        session.add(JobResult(
            analysis_id=analysis.id,
            agent_name=name,
            output_json=json.dumps(output),
        ))
    await session.commit()

    with (
        patch("backend.agents.resource_planner.ResourcePlannerAgent.run", new_callable=AsyncMock, return_value=rp),
        patch("backend.agents.cover_letter.CoverLetterAgent.run", new_callable=AsyncMock, return_value=cl),
        patch("backend.agents.resume_tailorer.ResumeTailorerAgent.run", new_callable=AsyncMock, return_value=rt),
    ):
        from backend.services.orchestrator import run_generate_pipeline

        events = []
        async for event in run_generate_pipeline(analysis.id, session):
            events.append(event)

    names = [e.name for e in events]
    assert names[0] == "pipeline_start"
    assert events[0].data["total_agents"] == 3
    assert names.count("agent_start") == 3
    assert names.count("agent_done") == 3
    assert names[-1] == "pipeline_done"

    done = events[-1]
    assert done.data["analysis_id"] == analysis.id
    assert done.data["evaluate_only"] is False
    assert done.data["score"] == 82
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
pytest tests/test_orchestrator/test_sse_sequence.py -v
```
Expected: `FAILED — cannot import name 'run_evaluate_pipeline'`

- [ ] **Step 3: Replace orchestrator.py**

```python
# backend/services/orchestrator.py
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import AgentError, JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)
from backend.services.profile_builder import build_compact_profile, get_or_build_profile


@dataclass
class SSEEvent:
    name: str
    data: dict[str, Any]


class _AgentProtocol(Protocol):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> Any: ...


async def run_evaluate_pipeline(
    jd: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 1: job_parser → match_scorer → gap_analyst.

    job_parser and match_scorer receive a compact profile (YAML + CV excerpt).
    gap_analyst receives the full merged profile.
    Saves an Analysis row with evaluate_only=True.
    """
    profile = await get_or_build_profile(db)
    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    for agent_name, agent, profile_str in phase1:
        yield SSEEvent("agent_start", {"agent": agent_name})
        try:
            output = await agent.run(profile_str, jd, prior)
            prior = prior.model_copy(update={agent_name: output})
            results[agent_name] = output.model_dump()
            yield SSEEvent("agent_done", {"agent": agent_name, "output": output.model_dump()})
        except AgentError as e:
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(e)})

    score = results.get("match_scorer", {}).get("score", 0)
    analysis = Analysis(
        jd_text=jd, profile_id=profile.id, partial=partial, evaluate_only=True
    )
    db.add(analysis)
    await db.flush()

    for name, output in results.items():
        db.add(
            JobResult(
                analysis_id=analysis.id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    await db.commit()

    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis.id,
            "score": score,
            "partial": partial,
            "evaluate_only": True,
        },
    )


async def run_generate_pipeline(
    analysis_id: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 2: resource_planner → [cover_letter ∥ resume_tailorer].

    Loads Phase 1 results from DB to rebuild PriorOutputs.
    Appends Phase 2 JobResult rows and sets evaluate_only=False on the Analysis.
    """
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None:
        yield SSEEvent(
            "pipeline_error", {"agent": "system", "error": f"Analysis {analysis_id} not found"}
        )
        return

    profile = (
        await db.execute(select(Profile).where(Profile.id == analysis.profile_id))
    ).scalar_one_or_none()
    full = profile.merged_profile if profile else ""

    # Rebuild PriorOutputs from stored Phase 1 results
    stored = (
        await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id))
    ).scalars().all()
    prior = PriorOutputs()
    for row in stored:
        if not row.output_json:
            continue
        data = json.loads(row.output_json)
        if row.agent_name == "job_parser":
            prior = prior.model_copy(
                update={"job_parser": JobParserOutput.model_validate(data)}
            )
        elif row.agent_name == "match_scorer":
            prior = prior.model_copy(
                update={"match_scorer": MatchScorerOutput.model_validate(data)}
            )
        elif row.agent_name == "gap_analyst":
            prior = prior.model_copy(
                update={"gap_analyst": GapAnalystOutput.model_validate(data)}
            )

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    results: dict[str, dict[str, Any]] = {}
    partial = False

    # resource_planner runs first (gap_analyst output feeds into it)
    yield SSEEvent("agent_start", {"agent": "resource_planner"})
    try:
        rp_output = await ResourcePlannerAgent().run(full, analysis.jd_text, prior)
        prior = prior.model_copy(update={"resource_planner": rp_output})
        results["resource_planner"] = rp_output.model_dump()
        yield SSEEvent(
            "agent_done", {"agent": "resource_planner", "output": rp_output.model_dump()}
        )
    except AgentError as e:
        partial = True
        yield SSEEvent("pipeline_error", {"agent": "resource_planner", "error": str(e)})

    # cover_letter + resume_tailorer run in parallel
    yield SSEEvent("agent_start", {"agent": "cover_letter"})
    yield SSEEvent("agent_start", {"agent": "resume_tailorer"})

    cl_result, rt_result = await asyncio.gather(
        CoverLetterAgent().run(full, analysis.jd_text, prior),
        ResumeTailorerAgent().run(full, analysis.jd_text, prior),
        return_exceptions=True,
    )

    for agent_name, result in [("cover_letter", cl_result), ("resume_tailorer", rt_result)]:
        if isinstance(result, BaseException):
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(result)})
        else:
            results[agent_name] = result.model_dump()
            yield SSEEvent(
                "agent_done", {"agent": agent_name, "output": result.model_dump()}
            )

    # Persist Phase 2 results and mark analysis complete
    for name, output in results.items():
        db.add(
            JobResult(
                analysis_id=analysis_id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    analysis.evaluate_only = False
    if partial:
        analysis.partial = True
    await db.commit()

    score = prior.match_scorer.score if prior.match_scorer else 0
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis_id,
            "score": score,
            "partial": partial or analysis.partial,
            "evaluate_only": False,
        },
    )
```

- [ ] **Step 4: Run orchestrator tests**

```bash
pytest tests/test_orchestrator/ -v
```
Expected: `2 passed`

---

## Task 5: Update analyse routes

**Files:**
- Modify: `backend/routes/analyse.py`

- [ ] **Step 1: Replace analyse.py**

```python
# backend/routes/analyse.py
from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import AnalyseRequest
from backend.services.orchestrator import run_evaluate_pipeline, run_generate_pipeline

router = APIRouter(tags=["analyse"])


async def _event_stream(jd: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_evaluate_pipeline(jd, db):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


async def _generate_stream(analysis_id: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_generate_pipeline(analysis_id, db):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


@router.post("/analyse")
async def analyse_job(
    request: AnalyseRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _event_stream(request.jd, db),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/analyse/generate/{analysis_id}")
async def generate_analysis(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _generate_stream(analysis_id, db),
        media_type="text/event-stream",
        headers=headers,
    )
```

- [ ] **Step 2: Run route tests**

```bash
pytest tests/test_routes/ -v
```
Expected: all pass (existing route tests should still pass; the endpoint shape is unchanged for `/analyse`)

---

## Task 6: Frontend — types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update types/index.ts**

Replace the file with:

```typescript
// Mirrors backend/schemas.py 1:1 — update both files when schemas change
export interface GapItem { skill: string; impact: string; rationale: string; }
export interface ResourceItem { skill: string; courses: string[]; books: string[]; projects: string[]; estimated_hours: number; }
export interface BulletItem { original: string; rewritten: string; rationale: string; }
export interface JobParserOutput { required_skills: string[]; nice_to_have: string[]; years_experience: number | null; role_type: string; seniority: string; }
export interface MatchScorerOutput { score: number; matched_skills: string[]; missing_skills: string[]; partial_matches: string[]; }
export interface GapAnalystOutput { critical_gaps: GapItem[]; nice_to_have_gaps: GapItem[]; }
export interface ResourcePlannerOutput { gaps: ResourceItem[]; }
export interface CoverLetterOutput { subject: string; body: string; tone_notes: string; }
export interface ResumeTailorerOutput { tailored_bullets: BulletItem[]; }
export interface ProfileResponse { id: string; yaml_data: string; cv_text: string; github_data: string; merged_profile: string; last_refreshed_at: string; github_last_fetched_at: string | null; warnings: string[]; }
export interface ProfileStatusResponse { profile_last_built_at: string; github_last_fetched_at: string | null; github_is_stale: boolean; github_stale_after_days: number; }
export interface GitHubRefreshResponse { repos_updated: number; github_last_fetched_at: string; profile: ProfileResponse; }
export interface AnalysisSummary { id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean; }
export interface AnalysisDetail {
  id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean;
  results: {
    job_parser?: JobParserOutput; match_scorer?: MatchScorerOutput;
    gap_analyst?: GapAnalystOutput; resource_planner?: ResourcePlannerOutput;
    cover_letter?: CoverLetterOutput; resume_tailorer?: ResumeTailorerOutput;
  };
}
export type AgentName = "job_parser"|"match_scorer"|"gap_analyst"|"resource_planner"|"cover_letter"|"resume_tailorer";
export const AGENT_ORDER: AgentName[] = ["job_parser","match_scorer","gap_analyst","resource_planner","cover_letter","resume_tailorer"];
export const PHASE1_AGENTS: AgentName[] = ["job_parser","match_scorer","gap_analyst"];
export const PHASE2_AGENTS: AgentName[] = ["resource_planner","cover_letter","resume_tailorer"];
export type AgentStatus = "pending"|"running"|"done"|"error";
export interface PipelineDoneData { analysis_id: string; score: number; partial: boolean; evaluate_only: boolean; }
export interface SSECallbacks {
  onPipelineStart?: (data: { total_agents: number }) => void;
  onAgentStart?: (data: { agent: AgentName }) => void;
  onAgentDone?: (data: { agent: AgentName; output: unknown }) => void;
  onPipelineError?: (data: { agent: AgentName; error: string }) => void;
  onPipelineDone?: (data: PipelineDoneData) => void;
}
```

- [ ] **Step 2: Update api/client.ts — extract SSE helper + add streamGenerate**

Replace the file with:

```typescript
import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  getProfile: () => get<ProfileResponse>("/profile"),
  refreshProfile: async (): Promise<ProfileResponse> => {
    const r = await fetch(`${BASE}/profile/refresh`, { method: "POST" });
    if (!r.ok) throw new Error(`Refresh failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  uploadCv: async (file: File): Promise<ProfileResponse> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${BASE}/profile/cv`, { method: "POST", body: form });
    if (!r.ok) throw new Error(`CV upload failed: ${r.status}`);
    return r.json() as Promise<ProfileResponse>;
  },
  getProfileStatus: () => get<ProfileStatusResponse>("/profile/status"),
  refreshGithub: async (): Promise<GitHubRefreshResponse> => {
    const r = await fetch(`${BASE}/profile/refresh/github`, { method: "POST" });
    if (!r.ok) throw new Error(`GitHub refresh failed: ${r.status}`);
    return r.json() as Promise<GitHubRefreshResponse>;
  },
  listHistory: (limit = 20, offset = 0) => get<AnalysisSummary[]>(`/history?limit=${limit}&offset=${offset}`),
  getAnalysis: (id: string) => get<AnalysisDetail>(`/analysis/${id}`),
};

function _streamSSE(url: string, init: RequestInit, callbacks: SSECallbacks): () => void {
  const controller = new AbortController();
  (async () => {
    const resp = await fetch(url, { ...init, signal: controller.signal });
    if (!resp.body) return;
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          if (!chunk.trim()) continue;
          const lines = chunk.split("\n");
          const eventLine = lines.find((l) => l.startsWith("event:"));
          const dataLine = lines.find((l) => l.startsWith("data:"));
          if (!eventLine || !dataLine) continue;
          const eventName = eventLine.replace("event:", "").trim();
          const data = JSON.parse(dataLine.replace("data:", "").trim());
          switch (eventName) {
            case "pipeline_start": callbacks.onPipelineStart?.(data); break;
            case "agent_start": callbacks.onAgentStart?.(data as { agent: AgentName }); break;
            case "agent_done": callbacks.onAgentDone?.(data); break;
            case "pipeline_error": callbacks.onPipelineError?.(data); break;
            case "pipeline_done":
              callbacks.onPipelineDone?.(data);
              controller.abort();
              return;
          }
        }
      }
    } catch (e) { if ((e as Error).name !== "AbortError") throw e; }
  })();
  return () => controller.abort();
}

export function streamAnalysis(jd: string, callbacks: SSECallbacks): () => void {
  return _streamSSE(
    `${BASE}/analyse`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jd }) },
    callbacks,
  );
}

export function streamGenerate(analysisId: string, callbacks: SSECallbacks): () => void {
  return _streamSSE(`${BASE}/analyse/generate/${analysisId}`, { method: "POST" }, callbacks);
}
```

---

## Task 7: Frontend — AnalyseJob.tsx two-phase UI

**Files:**
- Modify: `frontend/src/pages/AnalyseJob.tsx`

- [ ] **Step 1: Replace AnalyseJob.tsx**

```tsx
import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { streamAnalysis, streamGenerate } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { AGENT_ORDER } from "../types";
import type { AgentName, AgentStatus, PipelineDoneData } from "../types";

const initStates = () =>
  Object.fromEntries(AGENT_ORDER.map((a) => [a, "pending"])) as Record<AgentName, AgentStatus>;

type Phase = "idle" | "evaluating" | "evaluated" | "generating";

export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [states, setStates] = useState<Record<AgentName, AgentStatus>>(initStates());
  const [evalResult, setEvalResult] = useState<PipelineDoneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const navigate = useNavigate();

  const running = phase === "evaluating" || phase === "generating";

  const submit = () => {
    if (jd.trim().length < 50) { setError("JD must be at least 50 characters."); return; }
    setError(null);
    setPhase("evaluating");
    setStates(initStates());
    setEvalResult(null);
    cancelRef.current = streamAnalysis(jd, {
      onAgentStart: ({ agent }) => setStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: (data) => { setPhase("evaluated"); setEvalResult(data); },
    });
  };

  const generate = () => {
    if (!evalResult) return;
    setPhase("generating");
    setError(null);
    cancelRef.current = streamGenerate(evalResult.analysis_id, {
      onAgentStart: ({ agent }) => setStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: ({ analysis_id }) => navigate(`/results/${analysis_id}`),
    });
  };

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Analyse a Job</h1>
      <textarea
        className="w-full h-48 p-3 rounded-lg border border-slate-300 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Paste the full job description here…"
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        disabled={running}
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {phase === "idle" && (
        <button
          onClick={submit}
          className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Analyse
        </button>
      )}

      {phase === "evaluating" && (
        <button disabled className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium opacity-50">
          Evaluating…
        </button>
      )}

      {phase === "evaluated" && evalResult && (
        <div className="flex items-center gap-4 flex-wrap">
          <div className="text-2xl font-bold text-slate-900">
            {evalResult.score}
            <span className="text-base font-normal text-slate-500">/100</span>
          </div>
          <button
            onClick={generate}
            className="px-6 py-2 rounded-lg bg-green-600 text-white font-medium hover:bg-green-700"
          >
            Generate Documents
          </button>
          <button
            onClick={() => navigate(`/results/${evalResult.analysis_id}`)}
            className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm hover:bg-slate-50"
          >
            View Gaps Only
          </button>
        </div>
      )}

      {phase === "generating" && (
        <p className="text-sm text-slate-500">Generating cover letter and resume bullets…</p>
      )}

      {phase !== "idle" && <AgentProgress agentStates={states} />}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

---

## Task 8: Frontend — Results.tsx generate button

**Files:**
- Modify: `frontend/src/pages/Results.tsx`

- [ ] **Step 1: Replace Results.tsx**

```tsx
import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { api, streamGenerate } from "../api/client";
import type { AnalysisDetail, AgentName, AgentStatus } from "../types";
import { PHASE2_AGENTS } from "../types";
import { ScoreCard } from "../components/ScoreCard";
import { GapList } from "../components/GapList";
import { ResourcePanel } from "../components/ResourcePanel";
import { DocViewer } from "../components/DocViewer";

type Tab = "score" | "gaps" | "resources" | "letter" | "resume";
const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "gaps", label: "Gaps" },
  { id: "resources", label: "Resources" },
  { id: "letter", label: "Cover Letter" },
  { id: "resume", label: "Resume" },
];

export function Results() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [tab, setTab] = useState<Tab>("score");
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genStates, setGenStates] = useState<Partial<Record<AgentName, AgentStatus>>>({});
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (id) api.getAnalysis(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  const generate = () => {
    if (!data) return;
    setGenerating(true);
    setGenStates(Object.fromEntries(PHASE2_AGENTS.map((a) => [a, "pending"])));
    cancelRef.current = streamGenerate(data.id, {
      onAgentStart: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => setGenerating(false));
      },
    });
  };

  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!data) return <p className="p-6 text-slate-500">Loading…</p>;
  const r = data.results;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Results</h1>
      {data.partial && (
        <p className="text-amber-600 text-sm">⚠ Partial results — some agents failed.</p>
      )}

      {data.evaluate_only && !generating && (
        <div className="flex items-center gap-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800 flex-1">
            Evaluation complete. Generate your cover letter, resource plan, and resume bullets.
          </p>
          <button
            onClick={generate}
            className="shrink-0 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            Generate Documents
          </button>
        </div>
      )}

      {generating && (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <p className="text-sm text-slate-600 mb-2">Generating documents…</p>
          <div className="flex gap-3 text-xs text-slate-500">
            {PHASE2_AGENTS.map((a) => (
              <span key={a} className={genStates[a] === "done" ? "text-green-600" : genStates[a] === "running" ? "text-blue-600" : ""}>
                {a.replace("_", " ")} {genStates[a] === "done" ? "✓" : genStates[a] === "running" ? "…" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 border-b">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pt-2">
        {tab === "score" && r.match_scorer && (
          <ScoreCard
            score={r.match_scorer.score}
            matched={r.match_scorer.matched_skills}
            missing={r.match_scorer.missing_skills}
            partial={r.match_scorer.partial_matches}
          />
        )}
        {tab === "gaps" && r.gap_analyst && (
          <GapList
            critical={r.gap_analyst.critical_gaps}
            niceToHave={r.gap_analyst.nice_to_have_gaps}
          />
        )}
        {tab === "resources" && (
          r.resource_planner
            ? <ResourcePanel gaps={r.resource_planner.gaps} />
            : <p className="text-sm text-slate-400 italic">Generate documents to see resource plan.</p>
        )}
        {tab === "letter" && (
          r.cover_letter
            ? <DocViewer title="Cover Letter" content={r.cover_letter.body} filename="cover_letter.txt" />
            : <p className="text-sm text-slate-400 italic">Generate documents to see cover letter.</p>
        )}
        {tab === "resume" && (
          r.resume_tailorer
            ? (
              <div className="space-y-4">
                {r.resume_tailorer.tailored_bullets.map((b, i) => (
                  <div key={i} className="border rounded-lg p-4 space-y-2 text-sm">
                    <p className="text-slate-400 line-through">{b.original}</p>
                    <p className="text-slate-900 font-medium">{b.rewritten}</p>
                    <p className="text-xs text-slate-400 italic">{b.rationale}</p>
                  </div>
                ))}
              </div>
            )
            : <p className="text-sm text-slate-400 italic">Generate documents to see resume bullets.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 3: Run full test suite**

```bash
cd /path/to/Job_Ready_Agent && pytest --tb=short -q
```
Expected: all tests pass (coverage may be above 70%)
