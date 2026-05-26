# LLM Cost Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track every LLM call (cost, latency, cache hits) and surface it on a `/costs` dashboard.

**Architecture:** A shared `tracked_call()` helper in `instrumentation.py` wraps every Anthropic API call. Both `BaseAgent._call()` and `discovery.py`'s Stage 2 call route through it. A new `llm_calls` DB table stores one row per call. Two FastAPI endpoints aggregate the data for a React dashboard.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, FastAPI, React 18, TypeScript, Tailwind CSS, Anthropic SDK.

---

## File Map

| File | Change |
|---|---|
| `backend/services/cost_calculator.py` | Create — pricing table + `calculate_cost()` |
| `backend/services/instrumentation.py` | Create — `tracked_call()`, `log_cache_hit()`, `_write_llm_call()` |
| `backend/models.py` | Add `LLMCall` ORM model |
| `scripts/migrate.py` | Add step 16: `llm_calls` table |
| `backend/agents/base.py` | Add `with_tracking()`, update `_call()` to delegate to `tracked_call()` |
| `backend/services/orchestrator.py` | Create Analysis row before agent loop; wire tracking; log cache hits |
| `backend/services/discovery.py` | Replace direct `messages.create` with `tracked_call()` |
| `backend/schemas.py` | Add `CostSummary`, `RunCost`, `AgentCost` Pydantic models |
| `backend/routes/metrics.py` | Create — two cost endpoints |
| `backend/main.py` | Register metrics router |
| `frontend/src/types/index.ts` | Add `CostSummary`, `RunCost`, `AgentCost` TS interfaces |
| `frontend/src/api/client.ts` | Add `getCostSummary()`, `getCostRuns()` |
| `frontend/src/pages/Costs.tsx` | Create — dashboard page |
| `frontend/src/App.tsx` | Add `/costs` route + nav link |
| `tests/test_services/test_cost_calculator.py` | Create |
| `tests/test_services/test_instrumentation.py` | Create |
| `tests/test_routes/test_metrics.py` | Create |

---

### Task 1: Cost calculator module

**Files:**
- Create: `backend/services/cost_calculator.py`
- Create: `tests/test_services/test_cost_calculator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_cost_calculator.py
import pytest
from backend.services.cost_calculator import calculate_cost


def test_haiku_cost():
    # 1M input @ $0.80 + 1M output @ $4.00 = $4.80
    cost = calculate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == pytest.approx(4.80)


def test_sonnet_cost():
    # 1M input @ $3.00 + 1M output @ $15.00 = $18.00
    cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.00)


def test_unknown_model_falls_back_to_sonnet_rates():
    cost = calculate_cost("future-model", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.00)


def test_zero_tokens_returns_zero():
    assert calculate_cost("claude-sonnet-4-6", 0, 0) == 0.0


def test_small_real_call():
    # 1000 input + 200 output on haiku
    cost = calculate_cost("claude-haiku-4-5-20251001", 1000, 200)
    expected = (1000 * 0.80 + 200 * 4.00) / 1_000_000
    assert cost == pytest.approx(expected)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_services/test_cost_calculator.py -v 2>&1 | head -15
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `backend/services/cost_calculator.py`**

```python
from __future__ import annotations

COST_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_MILLION.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
```

- [ ] **Step 4: Run tests — expect 5 passed**

```bash
pytest tests/test_services/test_cost_calculator.py -v
```

Expected: 5 passed.

---

### Task 2: `LLMCall` ORM model + migration

**Files:**
- Modify: `backend/models.py`
- Modify: `scripts/migrate.py`

- [ ] **Step 1: Read `backend/models.py`** to find the existing imports and where to insert the new class (add it after `SavedJob`, before `DiscoveryRun`).

- [ ] **Step 2: Add `LLMCall` to `backend/models.py`**

Check existing imports — `Float` may not be imported yet. The full import line should include it:
```python
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
```

Add this class after `SavedJob`:

```python
class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    agent_name: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None
    )
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("discovery_runs.id"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

- [ ] **Step 3: Verify model imports**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python3 -c "from backend.models import LLMCall; print('LLMCall OK')"
```

Expected: `LLMCall OK`

- [ ] **Step 4: Add migration step 16 to `scripts/migrate.py`**

Read `scripts/migrate.py` first to find where step 15 ends. Add this block immediately after:

```python
    # 16. Create llm_calls table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id            TEXT PRIMARY KEY,
            agent_name    TEXT NOT NULL,
            model         TEXT NOT NULL,
            input_tokens  INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd      REAL NOT NULL DEFAULT 0.0,
            latency_ms    INTEGER NOT NULL DEFAULT 0,
            cache_hit     INTEGER NOT NULL DEFAULT 0,
            analysis_id   TEXT REFERENCES analyses(id),
            run_id        TEXT REFERENCES discovery_runs(id),
            created_at    TIMESTAMP NOT NULL
        )
    """)
    print("✓ llm_calls table ready")
```

- [ ] **Step 5: Run migration**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python3 scripts/migrate.py
```

Expected: output includes `✓ llm_calls table ready` and ends with `Migration complete.`

---

### Task 3: Instrumentation module

**Files:**
- Create: `backend/services/instrumentation.py`
- Create: `tests/test_services/test_instrumentation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_instrumentation.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.instrumentation import tracked_call, log_cache_hit


@pytest.fixture
def mock_client():
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="response text")]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    client.messages.create = AsyncMock(return_value=msg)
    return client, msg


@pytest.mark.asyncio
async def test_tracked_call_returns_message(mock_client):
    client, msg = mock_client
    result = await tracked_call(
        client, "test_agent", "claude-sonnet-4-6",
        system="s", messages=[]
    )
    assert result is msg


@pytest.mark.asyncio
async def test_tracked_call_without_db_does_not_raise(mock_client):
    client, _ = mock_client
    # db=None is the default — must not raise
    await tracked_call(client, "test_agent", "claude-sonnet-4-6", system="s", messages=[])


@pytest.mark.asyncio
async def test_tracked_call_db_failure_does_not_raise(mock_client):
    client, _ = mock_client
    bad_db = MagicMock()
    bad_db.add = MagicMock()
    bad_db.commit = AsyncMock(side_effect=Exception("DB is down"))
    # must return message even when DB write fails
    result = await tracked_call(
        client, "test_agent", "claude-sonnet-4-6",
        db=bad_db, system="s", messages=[]
    )
    assert result.content[0].text == "response text"


@pytest.mark.asyncio
async def test_log_cache_hit_db_failure_does_not_raise():
    bad_db = MagicMock()
    bad_db.add = MagicMock()
    bad_db.commit = AsyncMock(side_effect=Exception("DB is down"))
    # must not raise
    await log_cache_hit(bad_db, "match_scorer", "claude-sonnet-4-6")
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_services/test_instrumentation.py -v 2>&1 | head -15
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `backend/services/instrumentation.py`**

```python
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import LLMCall
from backend.services.cost_calculator import calculate_cost


async def tracked_call(
    client: anthropic.AsyncAnthropic,
    agent_name: str,
    model: str,
    *,
    db: AsyncSession | None = None,
    run_id: str | None = None,
    analysis_id: str | None = None,
    **create_kwargs: Any,
) -> anthropic.types.Message:
    start = time.monotonic()
    msg = await client.messages.create(model=model, **create_kwargs)  # type: ignore[arg-type]
    latency_ms = int((time.monotonic() - start) * 1000)
    if db is not None:
        cost = calculate_cost(model, msg.usage.input_tokens, msg.usage.output_tokens)
        await _write_llm_call(
            db,
            agent_name=agent_name,
            model=model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
            run_id=run_id,
            analysis_id=analysis_id,
        )
    return msg


async def log_cache_hit(
    db: AsyncSession,
    agent_name: str,
    model: str,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> None:
    await _write_llm_call(
        db,
        agent_name=agent_name,
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=1,
        cache_hit=True,
        run_id=run_id,
        analysis_id=analysis_id,
    )


async def _write_llm_call(
    db: AsyncSession,
    *,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    cache_hit: bool,
    run_id: str | None,
    analysis_id: str | None,
) -> None:
    try:
        row = LLMCall(
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            run_id=run_id,
            analysis_id=analysis_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.commit()
    except Exception:
        pass  # never break an LLM call due to tracking failure
```

- [ ] **Step 4: Run tests — expect 4 passed**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_services/test_instrumentation.py -v
```

Expected: 4 passed.

---

### Task 4: Wire `BaseAgent` to use `tracked_call()`

**Files:**
- Modify: `backend/agents/base.py`

- [ ] **Step 1: Read `backend/agents/base.py`** to confirm current `_call()` signature.

- [ ] **Step 2: Rewrite `backend/agents/base.py`**

The full updated file:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic

from backend.config import settings
from backend.schemas import PriorOutputs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 4096


class BaseAgent:
    model: str = SONNET

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._db: AsyncSession | None = None
        self._run_id: str | None = None
        self._analysis_id: str | None = None

    def with_tracking(
        self,
        db: AsyncSession,
        *,
        run_id: str | None = None,
        analysis_id: str | None = None,
    ) -> "BaseAgent":
        self._db = db
        self._run_id = run_id
        self._analysis_id = analysis_id
        return self

    def _load_prompt(self, name: str) -> str:
        return (PROMPTS_DIR / f"{name}.md").read_text()

    def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs) -> str:
        result = template.replace("{profile}", profile).replace("{jd}", jd)
        for field, value in prior.model_dump(exclude_none=True).items():
            result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
        return result

    async def _call(self, system: str, user: str) -> str:
        from backend.services.instrumentation import tracked_call
        msg = await tracked_call(
            self._client,
            type(self).__name__.lower(),
            self.model,
            db=self._db,
            run_id=self._run_id,
            analysis_id=self._analysis_id,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
```

- [ ] **Step 3: Verify no existing tests break**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_agents/ tests/test_services/test_instrumentation.py tests/test_services/test_cost_calculator.py -v 2>&1 | tail -15
```

Expected: all agent tests and new tests pass.

---

### Task 5: Orchestrator + discovery wiring

**Files:**
- Modify: `backend/services/orchestrator.py`
- Modify: `backend/services/discovery.py`

**Key concept being implemented here:** The Analysis row is now created *before* agents run (as a placeholder with `partial=True`) so that `analysis_id` is available for tracking. After agents finish, `analysis.partial` is updated to reflect the real result.

- [ ] **Step 1: Read both files in full** before making changes.

- [ ] **Step 2: Update `_run_phase1` in `backend/services/orchestrator.py`**

Add `run_id` parameter and restructure to create Analysis before agents:

```python
async def _run_phase1(
    jd: str,
    profile: Profile,
    db: AsyncSession,
    job_id: str | None = None,
    run_id: str | None = None,
    model: str = SONNET,
) -> Phase1Result:
    from backend.services.instrumentation import log_cache_hit

    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()
    cached = (
        await db.execute(
            select(Analysis).where(
                Analysis.jd_hash == jd_hash,
                Analysis.partial == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if cached is not None:
        await log_cache_hit(db, "phase1_cache", model, run_id=run_id, analysis_id=cached.id)
        score_row = (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id == cached.id,
                    JobResult.agent_name == "match_scorer",
                )
            )
        ).scalar_one_or_none()
        score = (
            json.loads(score_row.output_json).get("score", 0)
            if score_row and score_row.output_json
            else 0
        )
        return Phase1Result(
            analysis_id=cached.id,
            score=score,
            partial=cached.partial,
            prior=PriorOutputs(),
        )

    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    # Create placeholder Analysis row BEFORE agents run so analysis_id is
    # available for LLM call tracking.
    analysis = Analysis(
        jd_text=jd,
        profile_id=profile.id,
        partial=True,
        evaluate_only=True,
        jd_hash=jd_hash,
        job_id=job_id,
    )
    db.add(analysis)
    await db.flush()

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1_agents: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    for agent_name, agent, profile_str in phase1_agents:
        agent.model = model  # type: ignore[attr-defined]
        agent.with_tracking(db, run_id=run_id, analysis_id=analysis.id)  # type: ignore[attr-defined]
        try:
            output = await agent.run(profile_str, jd, prior)
            prior = prior.model_copy(update={agent_name: output})
            results[agent_name] = output.model_dump()
        except AgentError:
            partial = True

    analysis.partial = partial
    score = results.get("match_scorer", {}).get("score", 0)

    for name, data in results.items():
        db.add(JobResult(
            analysis_id=analysis.id,
            agent_name=name,
            output_json=json.dumps(data),
        ))
    await db.commit()

    return Phase1Result(
        analysis_id=analysis.id,
        score=score,
        partial=partial,
        prior=prior,
    )
```

- [ ] **Step 3: Update `run_evaluate_pipeline` in `backend/services/orchestrator.py`**

Apply the same pattern — create Analysis placeholder before phase 1 agents, wire tracking for phase 2:

```python
async def run_evaluate_pipeline(
    jd: str, db: AsyncSession, user_id: str | None = None
) -> AsyncGenerator[SSEEvent, None]:
    from backend.services.instrumentation import log_cache_hit

    profile = await get_or_build_profile(db, user_id=user_id)
    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()

    cached = (
        await db.execute(
            select(Analysis).where(
                Analysis.jd_hash == jd_hash,
                Analysis.partial == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if cached is not None:
        await log_cache_hit(db, "phase1_cache", SONNET, analysis_id=cached.id)
        score_row = (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id == cached.id,
                    JobResult.agent_name == "match_scorer",
                )
            )
        ).scalar_one_or_none()
        score = (
            json.loads(score_row.output_json).get("score", 0)
            if score_row and score_row.output_json
            else 0
        )
        yield SSEEvent(
            "pipeline_done",
            {
                "analysis_id": cached.id,
                "score": score,
                "partial": cached.partial,
                "evaluate_only": cached.evaluate_only,
            },
        )
        return

    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    # Create placeholder Analysis before agents so analysis_id is trackable
    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    analysis = Analysis(
        jd_text=jd, profile_id=profile.id, partial=True,
        evaluate_only=True, jd_hash=jd_hash, user_id=user_id
    )
    db.add(analysis)
    await db.flush()

    phase1: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    for agent_name, agent, profile_str in phase1:
        agent.with_tracking(db, analysis_id=analysis.id)  # type: ignore[attr-defined]
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
    analysis.partial = partial

    for name, output in results.items():
        db.add(JobResult(
            analysis_id=analysis.id,
            agent_name=name,
            output_json=json.dumps(output),
        ))
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
```

- [ ] **Step 4: Update `run_generate_pipeline` in `backend/services/orchestrator.py`**

Wire tracking for phase 2 agents (analysis already exists here):

In the `run_generate_pipeline` function, add `with_tracking` calls to the three agents. The `analysis` object is already loaded at the top of the function:

```python
    # resource_planner (existing code, add with_tracking):
    rp_agent = ResourcePlannerAgent()
    rp_agent.with_tracking(db, analysis_id=analysis.id)
    yield SSEEvent("agent_start", {"agent": "resource_planner"})
    try:
        rp_output = await rp_agent.run(full, analysis.jd_text, prior)
        ...

    # cover_letter + resume_tailorer (add with_tracking before gather):
    cl_agent = CoverLetterAgent()
    rt_agent = ResumeTailorerAgent()
    cl_agent.with_tracking(db, analysis_id=analysis.id)
    rt_agent.with_tracking(db, analysis_id=analysis.id)
    yield SSEEvent("agent_start", {"agent": "cover_letter"})
    yield SSEEvent("agent_start", {"agent": "resume_tailorer"})

    cl_result, rt_result = await asyncio.gather(
        cl_agent.run(full, analysis.jd_text, prior),
        rt_agent.run(full, analysis.jd_text, prior),
        return_exceptions=True,
    )
```

- [ ] **Step 5: Update `discovery.py` to use `tracked_call()`**

In `backend/services/discovery.py`, find `_stage2_check` and:

a) Add import at the top:
```python
from backend.services.instrumentation import tracked_call
```

b) Add the warning comment above the module-level client:
```python
# must use tracked_call() — not raw _anthropic_client.messages.create()
_anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
```

c) Update `_stage2_check` signature to accept `db` and `run_id`:
```python
async def _stage2_check(
    raw_text: str,
    compact_profile: str,
    db: AsyncSession | None = None,
    run_id: str | None = None,
) -> Stage2Result:
    system = (
        "You are evaluating job postings for a candidate.\n\n"
        f"Candidate summary:\n{compact_profile[:1000]}\n\n"
        "Evaluate if the job posting is relevant to this candidate. "
        'Respond with ONLY valid JSON: {"relevant": true/false, "reason": "one sentence", '
        '"title": "job title or empty string", "company": "company name or empty string", "location": "city/remote or null"}'
    )
    msg = await tracked_call(
        _anthropic_client,
        "stage2_haiku",
        HAIKU,
        db=db,
        run_id=run_id,
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": f"Job posting:\n{raw_text[:3000]}"}],
    )
    if not msg.content:
        raise ValueError("Empty response from Haiku")
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object in Haiku response: {raw!r}")
    data = json.loads(raw[start:end])
    return Stage2Result(
        relevant=bool(data.get("relevant", False)),
        reason=data.get("reason", ""),
        title=data.get("title", ""),
        company=data.get("company", ""),
        location=data.get("location"),
    )
```

d) Find where `_stage2_check` is called inside `_process_job` and update to pass `db` and `run_id`. The `run_id` comes from `job.run_id`:
```python
    s2 = await _stage2_check(job.raw_text, compact_profile, db=db, run_id=job.run_id)
```

e) Find where `_run_phase1` is called inside `_process_job` and pass `run_id=job.run_id`:
```python
    result = await _run_phase1(jd, profile, db, job_id=job.id, run_id=job.run_id, model=HAIKU)
```

- [ ] **Step 6: Run the full test suite to verify no regressions**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/ -v --ignore=tests/test_routes/test_status.py 2>&1 | tail -20
```

Expected: same pass/fail counts as before this task. New tests (cost_calculator, instrumentation) pass.

---

### Task 6: Cost schemas + metrics routes + tests

**Files:**
- Modify: `backend/schemas.py`
- Create: `backend/routes/metrics.py`
- Modify: `backend/main.py`
- Create: `tests/test_routes/test_metrics.py`

- [ ] **Step 1: Add cost schemas to `backend/schemas.py`**

Append to the end of `backend/schemas.py`:

```python
class AgentCost(BaseModel):
    agent_name: str
    calls: int
    cost_usd: float
    avg_latency_ms: int


class RunCost(BaseModel):
    id: str
    type: str  # "discovery" or "analysis"
    created_at: datetime
    total_cost_usd: float
    total_calls: int
    cached_calls: int
    latency_p50_ms: int
    agents: list[AgentCost]


class CostSummary(BaseModel):
    total_cost_usd: float
    total_calls: int
    real_calls: int
    cached_calls: int
    cache_hit_rate: float
    total_input_tokens: int
    total_output_tokens: int
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_routes/test_metrics.py
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from backend.models import LLMCall
from backend.services.auth_service import get_current_user
from backend.models import User


@pytest.fixture
def fake_user():
    return User(id="user-1", email="test@test.com", hashed_password="x",
                is_active=True, is_admin=True,
                created_at=datetime.now(timezone.utc))


@pytest.fixture
async def authed_client(app_client, fake_user):
    from backend.main import app
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_summary_empty_db(authed_client: AsyncClient):
    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calls"] == 0
    assert data["total_cost_usd"] == 0.0
    assert data["cache_hit_rate"] == 0.0


@pytest.mark.asyncio
async def test_summary_counts_calls(authed_client: AsyncClient, db_session):
    from datetime import datetime, timezone
    db_session.add(LLMCall(
        agent_name="match_scorer", model="claude-sonnet-4-6",
        input_tokens=1000, output_tokens=200, cost_usd=0.006,
        latency_ms=1200, cache_hit=False,
        created_at=datetime.now(timezone.utc),
    ))
    db_session.add(LLMCall(
        agent_name="phase1_cache", model="claude-sonnet-4-6",
        input_tokens=0, output_tokens=0, cost_usd=0.0,
        latency_ms=1, cache_hit=True,
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()
    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calls"] == 2
    assert data["real_calls"] == 1
    assert data["cached_calls"] == 1
    assert data["cache_hit_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_runs_empty_db(authed_client: AsyncClient):
    r = await authed_client.get("/api/metrics/costs/runs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_summary_requires_auth(app_client: AsyncClient):
    r = await app_client.get("/api/metrics/costs/summary")
    assert r.status_code == 401
```

- [ ] **Step 3: Run tests — expect ImportError or 404**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_routes/test_metrics.py -v 2>&1 | head -20
```

Expected: ImportError or connection errors — routes don't exist yet.

- [ ] **Step 4: Create `backend/routes/metrics.py`**

```python
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from backend.database import get_db
from backend.models import LLMCall, User
from backend.schemas import AgentCost, CostSummary, RunCost
from backend.services.auth_service import get_current_user

router = APIRouter(tags=["metrics"])


@router.get("/metrics/costs/summary", response_model=CostSummary)
async def get_cost_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostSummary:
    row = (
        await db.execute(
            select(
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == False, 1), else_=0)).label("real_calls"),
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("total_cost_usd"),
                func.coalesce(func.sum(LLMCall.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(LLMCall.output_tokens), 0).label("total_output_tokens"),
            )
        )
    ).one()
    total = row.total_calls or 0
    cached = row.cached_calls or 0
    return CostSummary(
        total_cost_usd=float(row.total_cost_usd or 0),
        total_calls=total,
        real_calls=row.real_calls or 0,
        cached_calls=cached,
        cache_hit_rate=cached / total if total else 0.0,
        total_input_tokens=row.total_input_tokens or 0,
        total_output_tokens=row.total_output_tokens or 0,
    )


@router.get("/metrics/costs/runs", response_model=list[RunCost])
async def get_cost_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunCost]:
    runs: list[RunCost] = []

    # Discovery runs
    disc_rows = (
        await db.execute(
            select(
                LLMCall.run_id,
                func.sum(LLMCall.cost_usd).label("total_cost_usd"),
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),
                func.min(LLMCall.created_at).label("created_at"),
            )
            .where(LLMCall.run_id.isnot(None))
            .group_by(LLMCall.run_id)
            .order_by(func.min(LLMCall.created_at).desc())
            .limit(20)
        )
    ).all()

    for dr in disc_rows:
        agents = await _agent_breakdown(db, run_id=dr.run_id)
        p50 = await _p50_latency(db, run_id=dr.run_id)
        runs.append(RunCost(
            id=dr.run_id,
            type="discovery",
            created_at=dr.created_at,
            total_cost_usd=float(dr.total_cost_usd or 0),
            total_calls=dr.total_calls,
            cached_calls=dr.cached_calls or 0,
            latency_p50_ms=p50,
            agents=agents,
        ))

    # Manual analyses
    anal_rows = (
        await db.execute(
            select(
                LLMCall.analysis_id,
                func.sum(LLMCall.cost_usd).label("total_cost_usd"),
                func.count(LLMCall.id).label("total_calls"),
                func.sum(case((LLMCall.cache_hit == True, 1), else_=0)).label("cached_calls"),
                func.min(LLMCall.created_at).label("created_at"),
            )
            .where(LLMCall.analysis_id.isnot(None), LLMCall.run_id.is_(None))
            .group_by(LLMCall.analysis_id)
            .order_by(func.min(LLMCall.created_at).desc())
            .limit(20)
        )
    ).all()

    for ar in anal_rows:
        agents = await _agent_breakdown(db, analysis_id=ar.analysis_id)
        p50 = await _p50_latency(db, analysis_id=ar.analysis_id)
        runs.append(RunCost(
            id=ar.analysis_id,
            type="analysis",
            created_at=ar.created_at,
            total_cost_usd=float(ar.total_cost_usd or 0),
            total_calls=ar.total_calls,
            cached_calls=ar.cached_calls or 0,
            latency_p50_ms=p50,
            agents=agents,
        ))

    runs.sort(key=lambda r: r.created_at, reverse=True)
    return runs


async def _agent_breakdown(
    db: AsyncSession,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> list[AgentCost]:
    q = (
        select(
            LLMCall.agent_name,
            func.count(LLMCall.id).label("calls"),
            func.coalesce(func.sum(LLMCall.cost_usd), 0.0).label("cost_usd"),
            func.coalesce(func.avg(LLMCall.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(LLMCall.cache_hit == False)  # noqa: E712
        .group_by(LLMCall.agent_name)
    )
    if run_id:
        q = q.where(LLMCall.run_id == run_id)
    else:
        q = q.where(LLMCall.analysis_id == analysis_id)
    rows = (await db.execute(q)).all()
    return [
        AgentCost(
            agent_name=r.agent_name,
            calls=r.calls,
            cost_usd=float(r.cost_usd),
            avg_latency_ms=int(r.avg_latency_ms or 0),
        )
        for r in rows
    ]


async def _p50_latency(
    db: AsyncSession,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> int:
    q = (
        select(LLMCall.latency_ms)
        .where(LLMCall.cache_hit == False)  # noqa: E712
        .limit(500)
    )
    if run_id:
        q = q.where(LLMCall.run_id == run_id)
    else:
        q = q.where(LLMCall.analysis_id == analysis_id)
    values = sorted((await db.execute(q)).scalars().all())
    return values[len(values) // 2] if values else 0
```

- [ ] **Step 5: Register metrics router in `backend/main.py`**

Add:
```python
from backend.routes.metrics import router as metrics_router
```
And:
```python
app.include_router(metrics_router, prefix=settings.api_prefix)
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_routes/test_metrics.py -v
```

Expected: 5 passed.

---

### Task 7: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Append to `frontend/src/types/index.ts`**

```typescript
export interface AgentCost {
  agent_name: string;
  calls: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export interface RunCost {
  id: string;
  type: "discovery" | "analysis";
  created_at: string;
  total_cost_usd: number;
  total_calls: number;
  cached_calls: number;
  latency_p50_ms: number;
  agents: AgentCost[];
}

export interface CostSummary {
  total_cost_usd: number;
  total_calls: number;
  real_calls: number;
  cached_calls: number;
  cache_hit_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
}
```

- [ ] **Step 2: Update import line in `frontend/src/api/client.ts`**

Add `AgentCost`, `RunCost`, `CostSummary` to the import:
```typescript
import type { ..., AgentCost, RunCost, CostSummary } from "../types";
```

- [ ] **Step 3: Add API methods to the `api` object in `frontend/src/api/client.ts`**

After the `logout` entry, add:
```typescript
  getCostSummary: () => get<CostSummary>("/metrics/costs/summary"),
  getCostRuns: () => get<RunCost[]>("/metrics/costs/runs"),
```

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit 2>&1
```

Expected: no errors.

---

### Task 8: Costs.tsx page + App.tsx route

**Files:**
- Create: `frontend/src/pages/Costs.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Costs.tsx`**

```typescript
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CostSummary, RunCost } from "../types";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function fmt(n: number, decimals = 4) {
  return n.toFixed(decimals);
}

export function Costs() {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [runs, setRuns] = useState<RunCost[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getCostSummary(), api.getCostRuns()])
      .then(([s, r]) => { setSummary(s); setRuns(r); })
      .catch((e) => setError((e as Error).message));
  }, []);

  const agentTotals = runs.flatMap((r) => r.agents).reduce<Record<string, { calls: number; cost_usd: number; total_latency: number }>>((acc, a) => {
    const prev = acc[a.agent_name] ?? { calls: 0, cost_usd: 0, total_latency: 0 };
    acc[a.agent_name] = {
      calls: prev.calls + a.calls,
      cost_usd: prev.cost_usd + a.cost_usd,
      total_latency: prev.total_latency + a.avg_latency_ms * a.calls,
    };
    return acc;
  }, {});

  const totalCost = summary?.total_cost_usd ?? 0;

  return (
    <div className="max-w-4xl mx-auto px-6 space-y-8">
      <h1 className="text-xl font-bold text-slate-900">LLM Cost Dashboard</h1>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Spent" value={`$${fmt(summary.total_cost_usd)}`} />
          <StatCard label="LLM Calls" value={summary.total_calls.toLocaleString()} />
          <StatCard label="Cache Hit Rate" value={`${(summary.cache_hit_rate * 100).toFixed(1)}%`} />
          <StatCard label="Real Calls" value={summary.real_calls.toLocaleString()} />
        </div>
      )}

      {runs.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-700">Runs</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="px-5 py-2">Date</th>
                <th className="px-5 py-2">Type</th>
                <th className="px-5 py-2">Calls</th>
                <th className="px-5 py-2">Cost</th>
                <th className="px-5 py-2">P50 Latency</th>
                <th className="px-5 py-2">Cache Hits</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <>
                  <tr
                    key={r.id}
                    onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                    className="border-b border-slate-50 hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-5 py-2 text-slate-600">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="px-5 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${r.type === "discovery" ? "bg-blue-50 text-blue-600 border-blue-100" : "bg-emerald-50 text-emerald-600 border-emerald-100"}`}>
                        {r.type}
                      </span>
                    </td>
                    <td className="px-5 py-2 text-slate-700">{r.total_calls}</td>
                    <td className="px-5 py-2 font-mono text-slate-700">${fmt(r.total_cost_usd)}</td>
                    <td className="px-5 py-2 text-slate-700">{r.latency_p50_ms}ms</td>
                    <td className="px-5 py-2 text-slate-700">{r.cached_calls}</td>
                  </tr>
                  {expandedId === r.id && r.agents.length > 0 && (
                    <tr key={`${r.id}-agents`} className="bg-slate-50 border-b border-slate-100">
                      <td colSpan={6} className="px-8 py-3">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left text-slate-500">
                              <th className="pb-1">Agent</th>
                              <th className="pb-1">Calls</th>
                              <th className="pb-1">Cost</th>
                              <th className="pb-1">Avg Latency</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.agents.map((a) => (
                              <tr key={a.agent_name}>
                                <td className="py-0.5 font-mono text-slate-700">{a.agent_name}</td>
                                <td className="py-0.5 text-slate-600">{a.calls}</td>
                                <td className="py-0.5 font-mono text-slate-700">${fmt(a.cost_usd)}</td>
                                <td className="py-0.5 text-slate-600">{a.avg_latency_ms}ms</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(agentTotals).length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-700">Agent Totals (all runs)</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="px-5 py-2">Agent</th>
                <th className="px-5 py-2">Total Calls</th>
                <th className="px-5 py-2">Total Cost</th>
                <th className="px-5 py-2">Avg Latency</th>
                <th className="px-5 py-2">% of Spend</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(agentTotals)
                .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
                .map(([name, data]) => (
                  <tr key={name} className="border-b border-slate-50">
                    <td className="px-5 py-2 font-mono text-slate-700">{name}</td>
                    <td className="px-5 py-2 text-slate-600">{data.calls}</td>
                    <td className="px-5 py-2 font-mono text-slate-700">${fmt(data.cost_usd)}</td>
                    <td className="px-5 py-2 text-slate-600">
                      {data.calls > 0 ? Math.round(data.total_latency / data.calls) : 0}ms
                    </td>
                    <td className="px-5 py-2 text-slate-600">
                      {totalCost > 0 ? ((data.cost_usd / totalCost) * 100).toFixed(1) : "0"}%
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {!summary && !error && (
        <p className="text-sm text-slate-400">Loading…</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update `frontend/src/App.tsx`**

Add import:
```typescript
import { Costs } from "./pages/Costs";
```

Add nav link (inside the `Nav` component, after the Saved link):
```tsx
<NavLink to="/costs" className={link}>Costs</NavLink>
```

Add route (inside `<Routes>`, after the saved route):
```tsx
<Route path="/costs" element={<ProtectedRoute><Costs /></ProtectedRoute>} />
```

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 4: Run full backend test suite**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/ -v --ignore=tests/test_routes/test_status.py 2>&1 | tail -20
```

Expected: new metrics tests pass, no regressions.
