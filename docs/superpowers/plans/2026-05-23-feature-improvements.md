# Feature Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add analysis caching, application status tracking, recurring gaps insights dashboard, cover letter tone picker, and LLM-based profile compression to JobFit Agent.

**Architecture:** Five independent features sharing one DB migration pass. The backend is FastAPI + SQLAlchemy async; the frontend is React + TypeScript + Tailwind. Each feature is self-contained: no feature depends on another being done first. Tasks interleave backend and frontend work per feature so each commit is shippable.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · SQLite + aiosqlite · Anthropic SDK (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`) · React 18 · TypeScript · Tailwind CSS v4

---

## File Structure

**Created:**
- `backend/routes/insights.py` — `GET /api/insights/gaps` aggregation endpoint
- `frontend/src/pages/Insights.tsx` — recurring gaps dashboard page
- `tests/test_orchestrator/test_analysis_caching.py` — cache hit / miss tests
- `tests/test_routes/test_insights.py` — gaps aggregation tests
- `tests/test_routes/test_status.py` — PATCH status endpoint tests
- `tests/test_agents/test_cover_letter_tone.py` — tone slot injection test
- `tests/test_services/test_profile_summary.py` — LLM summary storage test

**Modified:**
- `backend/models.py` — `Analysis.jd_hash`, `Analysis.status`, `Profile.profile_summary`
- `backend/schemas.py` — `InsightGap`, `GapsInsightResponse`, `UpdateStatusRequest`, `GenerateRequest`, `AnalysisSummary.status`
- `backend/services/orchestrator.py` — cache check in Phase 1; `tone` param in Phase 2; use `profile_summary`
- `backend/services/profile_builder.py` — `_summarise_profile()` Haiku call; store on `Profile`
- `backend/agents/base.py` — `_inject(**extras)` for extra slot substitution
- `backend/agents/cover_letter.py` — `run(..., tone)` param
- `backend/prompts/cover_letter.md` — `{tone}` slot
- `backend/routes/analyse.py` — `generate_analysis` reads `GenerateRequest` body
- `backend/routes/history.py` — `PATCH /analysis/{id}/status` endpoint
- `backend/main.py` — register insights router
- `scripts/migrate.py` — steps for `jd_hash`, `status`, `profile_summary` columns
- `frontend/src/types/index.ts` — `InsightGap`, `GapsInsightResponse`, `status` on `AnalysisSummary`, `tone` literals
- `frontend/src/api/client.ts` — `getInsights()`, `updateStatus()`, `streamGenerate` tone param
- `frontend/src/pages/AnalyseJob.tsx` — tone dropdown in evaluated phase
- `frontend/src/pages/Results.tsx` — tone picker in generate banner
- `frontend/src/pages/History.tsx` — status badges, inline dropdown, top filter
- `frontend/src/App.tsx` — `/insights` route + Insights nav item
- `tests/test_orchestrator/test_sse_sequence.py` — fix `run_generate_pipeline` call signature

---

## Task 1: Analysis Caching

**Context:** `run_evaluate_pipeline` currently always runs all three Phase 1 agents, even when the same JD+profile combination was already analysed. We add a `jd_hash` column to `Analysis` and return the cached result immediately when a non-partial match exists.

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `scripts/migrate.py`
- Create: `tests/test_orchestrator/test_analysis_caching.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orchestrator/test_analysis_caching.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
)

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


async def test_cache_hit_returns_existing_analysis(session):
    """When same JD+profile already analysed, pipeline_done fires immediately."""
    profile = Profile(
        id="p1",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    # Pre-seed a complete analysis with the same JD
    import hashlib
    jd_hash = hashlib.sha256(f"{JD}::p1".encode()).hexdigest()
    existing = Analysis(
        jd_text=JD,
        profile_id="p1",
        partial=False,
        evaluate_only=True,
        jd_hash=jd_hash,
    )
    session.add(existing)
    await session.flush()
    session.add(JobResult(
        analysis_id=existing.id,
        agent_name="match_scorer",
        output_json=json.dumps({"score": 75, "matched_skills": [], "missing_skills": [], "partial_matches": []}),
    ))
    await session.commit()

    with patch(
        "backend.services.orchestrator.get_or_build_profile",
        new_callable=AsyncMock,
        return_value=profile,
    ):
        from backend.services.orchestrator import run_evaluate_pipeline
        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    # Should only have pipeline_done — no agent_start events
    assert len(events) == 1
    assert events[0].name == "pipeline_done"
    assert events[0].data["analysis_id"] == existing.id
    assert events[0].data["score"] == 75


async def test_cache_miss_runs_pipeline(session):
    """When no cached analysis exists, all three Phase 1 agents run."""
    profile = Profile(
        id="p2",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )

    jp = JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="ML", seniority="Senior")
    ms = MatchScorerOutput(score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch("backend.services.orchestrator.get_or_build_profile", new_callable=AsyncMock, return_value=profile),
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline
        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    names = [e.name for e in events]
    assert "agent_start" in names
    assert names[-1] == "pipeline_done"


async def test_partial_cache_not_reused(session):
    """Partial (failed) analysis is never returned as a cache hit."""
    profile = Profile(
        id="p3",
        yaml_data="x",
        cv_text="",
        github_data="{}",
        merged_profile="profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()

    import hashlib
    jd_hash = hashlib.sha256(f"{JD}::p3".encode()).hexdigest()
    partial_analysis = Analysis(
        jd_text=JD, profile_id="p3", partial=True, evaluate_only=True, jd_hash=jd_hash
    )
    session.add(partial_analysis)
    await session.commit()

    jp = JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="ML", seniority="Senior")
    ms = MatchScorerOutput(score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch("backend.services.orchestrator.get_or_build_profile", new_callable=AsyncMock, return_value=profile),
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline
        events = []
        async for event in run_evaluate_pipeline(JD, session):
            events.append(event)

    names = [e.name for e in events]
    assert "agent_start" in names  # ran fresh — partial not reused
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_orchestrator/test_analysis_caching.py -v
```
Expected: FAIL — `Analysis` has no attribute `jd_hash`

- [ ] **Step 3: Add `jd_hash` to `Analysis` in `backend/models.py`**

The current `Analysis` class ends at line 46. Add `jd_hash` after `evaluate_only`:

```python
class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluate_only: Mapped[bool] = mapped_column(Boolean, default=False)
    jd_hash: Mapped[str] = mapped_column(String, default="", index=True)
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")
```

- [ ] **Step 4: Add cache check to `run_evaluate_pipeline` in `backend/services/orchestrator.py`**

Add `import hashlib` at the top of the file (alongside existing imports). Then replace the beginning of `run_evaluate_pipeline` (after the docstring, before `yield SSEEvent("pipeline_start", ...)`):

```python
async def run_evaluate_pipeline(
    jd: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 1: job_parser → match_scorer → gap_analyst.

    job_parser and match_scorer receive a compact profile (YAML + CV excerpt).
    gap_analyst receives the full merged profile.
    Saves an Analysis row with evaluate_only=True.
    Returns cached result immediately if same JD+profile was already analysed.
    """
    import hashlib

    profile = await get_or_build_profile(db)
    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()

    # Cache check: return immediately if a complete analysis already exists for this JD+profile
    cached = (
        await db.execute(
            select(Analysis).where(
                Analysis.jd_hash == jd_hash,
                Analysis.partial == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if cached is not None:
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
        jd_text=jd, profile_id=profile.id, partial=partial, evaluate_only=True, jd_hash=jd_hash
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
```

- [ ] **Step 5: Add migration step to `scripts/migrate.py`**

Add after the existing step 3 (evaluate_only), before `conn.commit()`:

```python
    # 4. Add jd_hash to analyses (DEFAULT '' for existing rows)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN jd_hash TEXT NOT NULL DEFAULT ''")
        print("✓ Added jd_hash to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- jd_hash already exists, skipping")
        else:
            raise
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
pytest tests/test_orchestrator/test_analysis_caching.py -v
```
Expected: 3 PASSED

- [ ] **Step 7: Run full suite to check for regressions**

```bash
pytest tests/ -v --ignore=tests/test_services/test_profile_builder.py --ignore=tests/test_routes/test_profile.py
```
Expected: all tests pass (the two ignored files have pre-existing failures unrelated to this work)

---

## Task 2: Application Tracker (Backend)

**Context:** Add a nullable `status` field to `Analysis` so users can track where they are in the application process. Status values: `applied`, `interviewing`, `rejected`, `offer`. A `PATCH /api/analysis/{id}/status` endpoint sets the value. History list now returns `status` so the frontend can display it.

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/schemas.py`
- Modify: `backend/routes/history.py`
- Modify: `scripts/migrate.py`
- Create: `tests/test_routes/test_status.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes/test_status.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import Analysis, Profile
from datetime import datetime, timezone


@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def seeded_analysis(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
        profile = Profile(
            id="p1",
            yaml_data="x",
            cv_text="",
            github_data="{}",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(profile)
        await s.flush()
        analysis = Analysis(
            jd_text="Python ML engineer role. " * 5,
            profile_id=profile.id,
            partial=False,
            evaluate_only=False,
        )
        s.add(analysis)
        await s.commit()
        return analysis.id


async def test_patch_status_sets_value(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"


async def test_patch_status_to_none_clears_value(app_client, seeded_analysis):
    # Set first
    await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": "applied"})
    # Clear
    resp = await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": None})
    assert resp.status_code == 200
    assert resp.json()["status"] is None


async def test_patch_status_invalid_value_returns_422(app_client, seeded_analysis):
    resp = await app_client.patch(
        f"/api/analysis/{seeded_analysis}/status",
        json={"status": "ghosted"},
    )
    assert resp.status_code == 422


async def test_patch_status_not_found_returns_404(app_client):
    resp = await app_client.patch(
        "/api/analysis/nonexistent-id/status",
        json={"status": "applied"},
    )
    assert resp.status_code == 404


async def test_history_list_includes_status(app_client, seeded_analysis):
    await app_client.patch(f"/api/analysis/{seeded_analysis}/status", json={"status": "interviewing"})
    resp = await app_client.get("/api/history")
    assert resp.status_code == 200
    items = resp.json()
    assert any(item["status"] == "interviewing" for item in items)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_routes/test_status.py -v
```
Expected: FAIL — `Analysis` has no attribute `status`

- [ ] **Step 3: Add `status` to `Analysis` in `backend/models.py`**

Add after `jd_hash` (or `evaluate_only` if Task 1 not yet done):

```python
class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluate_only: Mapped[bool] = mapped_column(Boolean, default=False)
    jd_hash: Mapped[str] = mapped_column(String, default="", index=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")
```

(If Task 1 is not done, omit `jd_hash` — add only `status`.)

- [ ] **Step 4: Add `UpdateStatusRequest` and update `AnalysisSummary` in `backend/schemas.py`**

Add `UpdateStatusRequest` after `AnalyseRequest`:

```python
_VALID_STATUSES = {"applied", "interviewing", "rejected", "offer"}

class UpdateStatusRequest(BaseModel):
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)} or null")
        return v
```

Also add `from pydantic import field_validator` to the import at the top:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

Update `AnalysisSummary`:

```python
class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    evaluate_only: bool
    status: str | None = None
```

- [ ] **Step 5: Add `PATCH /analysis/{id}/status` endpoint to `backend/routes/history.py`**

Add these imports at the top:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Analysis
from backend.schemas import AnalysisDetail, AnalysisSummary, UpdateStatusRequest
```

Add the new endpoint after `get_analysis`:

```python
@router.patch("/analysis/{analysis_id}/status", response_model=AnalysisSummary)
async def update_analysis_status(
    analysis_id: str,
    request: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalysisSummary:
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    analysis.status = request.status
    await db.commit()
    await db.refresh(analysis)
    return AnalysisSummary.model_validate(analysis)
```

- [ ] **Step 6: Add migration step to `scripts/migrate.py`**

Add after the `jd_hash` step (or after step 3 if Task 1 not done), before `conn.commit()`:

```python
    # 5. Add status to analyses (nullable, no default)
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN status TEXT")
        print("✓ Added status to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- status already exists, skipping")
        else:
            raise
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
pytest tests/test_routes/test_status.py -v
```
Expected: 5 PASSED

---

## Task 3: Application Tracker (Frontend)

**Context:** History page needs to show the current application status badge next to each row, let the user change it inline, and filter the list by status. Backend endpoint from Task 2 is now live.

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/History.tsx`

- [ ] **Step 1: Update `AnalysisSummary` in `frontend/src/types/index.ts`**

Change the existing `AnalysisSummary` interface (line 14) to add `status`:

```typescript
export interface AnalysisSummary { id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; evaluate_only: boolean; status: string | null; }
```

- [ ] **Step 2: Add `updateStatus` to `frontend/src/api/client.ts`**

Add to the `api` object (after `getAnalysis`):

```typescript
  updateStatus: async (id: string, status: string | null): Promise<AnalysisSummary> => {
    const r = await fetch(`${BASE}/analysis/${id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!r.ok) throw new Error(`Status update failed: ${r.status}`);
    return r.json() as Promise<AnalysisSummary>;
  },
```

- [ ] **Step 3: Rewrite `frontend/src/pages/History.tsx`**

Replace the entire file:

```tsx
import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AnalysisSummary } from "../types";

const STATUSES = ["applied", "interviewing", "rejected", "offer"] as const;
type AppStatus = (typeof STATUSES)[number] | null;

const STATUS_STYLE: Record<string, string> = {
  applied: "bg-blue-100 text-blue-700",
  interviewing: "bg-amber-100 text-amber-700",
  rejected: "bg-red-100 text-red-600",
  offer: "bg-green-100 text-green-700",
};

export function History() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<AppStatus | "all">("all");

  useEffect(() => {
    api.listHistory().then(setItems).finally(() => setLoading(false));
  }, []);

  const handleStatusChange = async (id: string, status: AppStatus) => {
    try {
      const updated = await api.updateStatus(id, status);
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    } catch {
      // silently ignore — UI stays unchanged on error
    }
  };

  const visible =
    filter === "all" ? items : items.filter((item) => item.status === filter);

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">History</h1>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as AppStatus | "all")}
          className="px-3 py-1.5 text-sm rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {!visible.length && (
        <p className="text-slate-500 text-sm">
          {filter === "all" ? "No analyses yet." : `No analyses with status "${filter}".`}
        </p>
      )}

      <div className="space-y-2">
        {visible.map((item) => (
          <div key={item.id} className="flex items-start gap-3 p-4 rounded-lg border hover:bg-slate-50">
            <Link to={`/results/${item.id}`} className="flex-1 min-w-0">
              <p className="text-sm text-slate-700 truncate">{item.jd_text.slice(0, 120)}…</p>
              <p className="text-xs text-slate-400 mt-1">{new Date(item.created_at).toLocaleString()}</p>
              {item.partial && <span className="text-xs text-amber-600">partial</span>}
            </Link>
            <div onClick={(e) => e.stopPropagation()} className="shrink-0">
              <select
                value={item.status ?? ""}
                onChange={(e) =>
                  handleStatusChange(item.id, (e.target.value || null) as AppStatus)
                }
                className={`text-xs px-2 py-1 rounded-full border-0 font-medium cursor-pointer ${
                  item.status ? STATUS_STYLE[item.status] : "bg-slate-100 text-slate-500"
                }`}
              >
                <option value="">Not tracked</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Task 4: Recurring Gaps Dashboard (Backend)

**Context:** Aggregate `critical_gaps` from every `gap_analyst` JobResult row. Return the top 20 recurring gap skills with counts. No new DB schema needed — we just query existing `job_results` rows.

**Files:**
- Modify: `backend/schemas.py`
- Create: `backend/routes/insights.py`
- Modify: `backend/main.py`
- Create: `tests/test_routes/test_insights.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes/test_insights.py
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base, get_db
from backend.models import Analysis, JobResult, Profile


@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_client(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    from backend.main import app

    async def override_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def seeded_gap_results(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
        profile = Profile(
            id="p1",
            yaml_data="x",
            cv_text="",
            github_data="{}",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
        )
        s.add(profile)
        await s.flush()

        for i, gaps in enumerate([
            [{"skill": "Kubernetes", "impact": "high", "rationale": "r"},
             {"skill": "AWS", "impact": "medium", "rationale": "r"}],
            [{"skill": "Kubernetes", "impact": "high", "rationale": "r"},
             {"skill": "Terraform", "impact": "low", "rationale": "r"}],
            [{"skill": "Kubernetes", "impact": "high", "rationale": "r"}],
        ]):
            analysis = Analysis(
                jd_text=f"JD {i}",
                profile_id="p1",
                partial=False,
                evaluate_only=False,
            )
            s.add(analysis)
            await s.flush()
            s.add(JobResult(
                analysis_id=analysis.id,
                agent_name="gap_analyst",
                output_json=json.dumps({"critical_gaps": gaps, "nice_to_have_gaps": []}),
            ))
        await s.commit()


async def test_insights_gaps_returns_sorted_by_count(app_client, seeded_gap_results):
    resp = await app_client.get("/api/insights/gaps")
    assert resp.status_code == 200
    data = resp.json()
    gaps = data["gaps"]
    assert gaps[0]["skill"] == "Kubernetes"
    assert gaps[0]["count"] == 3


async def test_insights_gaps_includes_all_recurring_skills(app_client, seeded_gap_results):
    resp = await app_client.get("/api/insights/gaps")
    skills = {g["skill"] for g in resp.json()["gaps"]}
    assert "Kubernetes" in skills
    assert "AWS" in skills
    assert "Terraform" in skills


async def test_insights_gaps_empty_when_no_analyses(app_client):
    resp = await app_client.get("/api/insights/gaps")
    assert resp.status_code == 200
    assert resp.json()["gaps"] == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_routes/test_insights.py -v
```
Expected: FAIL — `/api/insights/gaps` route not found

- [ ] **Step 3: Add `InsightGap` and `GapsInsightResponse` to `backend/schemas.py`**

Add after `GapItem`:

```python
class InsightGap(BaseModel):
    skill: str
    count: int
    impact: str


class GapsInsightResponse(BaseModel):
    gaps: list[InsightGap]
```

- [ ] **Step 4: Create `backend/routes/insights.py`**

```python
from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import JobResult
from backend.schemas import GapsInsightResponse, InsightGap

router = APIRouter(tags=["insights"])


@router.get("/insights/gaps", response_model=GapsInsightResponse)
async def get_gaps_insight(db: AsyncSession = Depends(get_db)) -> GapsInsightResponse:
    rows = (
        await db.execute(
            select(JobResult).where(JobResult.agent_name == "gap_analyst")
        )
    ).scalars().all()

    counts: Counter[str] = Counter()
    impacts: dict[str, str] = {}

    for row in rows:
        if not row.output_json:
            continue
        data = json.loads(row.output_json)
        for gap in data.get("critical_gaps", []):
            skill = gap.get("skill", "").strip()
            if skill:
                counts[skill] += 1
                impacts[skill] = gap.get("impact", "")

    gaps = [
        InsightGap(skill=skill, count=count, impact=impacts[skill])
        for skill, count in counts.most_common(20)
    ]
    return GapsInsightResponse(gaps=gaps)
```

- [ ] **Step 5: Register the insights router in `backend/main.py`**

Add import after existing route imports:

```python
from backend.routes.insights import router as insights_router
```

Add after `app.include_router(history_router, ...)`:

```python
app.include_router(insights_router, prefix=settings.api_prefix)
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
pytest tests/test_routes/test_insights.py -v
```
Expected: 3 PASSED

---

## Task 5: Recurring Gaps Dashboard (Frontend)

**Context:** Add a new `/insights` page that fetches `GET /api/insights/gaps` and displays a ranked list of recurring skill gaps with counts. Add it to the nav alongside Profile, Analyse, History.

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/Insights.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add `InsightGap` and `GapsInsightResponse` to `frontend/src/types/index.ts`**

Append to the end of the file:

```typescript
export interface InsightGap { skill: string; count: number; impact: string; }
export interface GapsInsightResponse { gaps: InsightGap[]; }
```

- [ ] **Step 2: Add `getInsights` to `frontend/src/api/client.ts`**

Add the import at the top (update existing import line):

```typescript
import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks, GapsInsightResponse } from "../types";
```

Add to the `api` object (after `updateStatus`):

```typescript
  getInsights: () => get<GapsInsightResponse>("/insights/gaps"),
```

- [ ] **Step 3: Create `frontend/src/pages/Insights.tsx`**

```tsx
import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { InsightGap } from "../types";

const IMPACT_STYLE: Record<string, string> = {
  high: "text-red-600",
  medium: "text-amber-600",
  low: "text-slate-500",
};

export function Insights() {
  const [gaps, setGaps] = useState<InsightGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInsights()
      .then((r) => setGaps(r.gaps))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Recurring Skill Gaps</h1>
      <p className="text-sm text-slate-500">
        Skills that appear as critical gaps across all your past analyses, ranked by frequency.
      </p>

      {!gaps.length && (
        <p className="text-slate-400 text-sm italic">No analyses yet. Run an analysis to see patterns.</p>
      )}

      <div className="space-y-2">
        {gaps.map((gap, i) => (
          <div key={gap.skill} className="flex items-center gap-4 p-3 rounded-lg border bg-white">
            <span className="text-lg font-bold text-slate-300 w-6 text-right shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900">{gap.skill}</p>
              <p className={`text-xs capitalize ${IMPACT_STYLE[gap.impact] ?? "text-slate-500"}`}>
                {gap.impact} impact
              </p>
            </div>
            <span className="shrink-0 text-sm font-semibold text-slate-600">
              {gap.count}×
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add `/insights` route and nav item to `frontend/src/App.tsx`**

Add the import after existing page imports:

```tsx
import { Insights } from "./pages/Insights";
```

Add nav link after the History link:

```tsx
<NavLink to="/insights" className={link}>Insights</NavLink>
```

Add route inside `<Routes>` after the history route:

```tsx
<Route path="/insights" element={<Insights />} />
```

The full `App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { History } from "./pages/History";
import { Insights } from "./pages/Insights";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium rounded-md ${isActive ? "bg-blue-100 text-blue-700" : "text-slate-600 hover:text-slate-900"}`;

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center gap-4">
          <span className="font-bold text-slate-900 mr-4">JobFit</span>
          <NavLink to="/" end className={link}>Profile</NavLink>
          <NavLink to="/analyse" className={link}>Analyse</NavLink>
          <NavLink to="/history" className={link}>History</NavLink>
          <NavLink to="/insights" className={link}>Insights</NavLink>
        </nav>
        <main className="py-8">
          <Routes>
            <Route path="/" element={<ProfileSetup />} />
            <Route path="/analyse" element={<AnalyseJob />} />
            <Route path="/results/:id" element={<Results />} />
            <Route path="/history" element={<History />} />
            <Route path="/insights" element={<Insights />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

---

## Task 6: Cover Letter Tone Picker (Backend)

**Context:** Add a `tone` parameter to Phase 2 pipeline so users can request Professional, Conversational, or Direct cover letters. Tone travels from the frontend dropdown → `GenerateRequest` body → orchestrator → `CoverLetterAgent.run()` → prompt slot `{tone}`.

The `_inject` method in `BaseAgent` currently only handles `{profile}`, `{jd}`, and `{prior.*}` slots. We extend it with `**extras` for arbitrary extra slots without breaking any other agents.

**Files:**
- Modify: `backend/prompts/cover_letter.md`
- Modify: `backend/agents/base.py`
- Modify: `backend/agents/cover_letter.py`
- Modify: `backend/schemas.py`
- Modify: `backend/routes/analyse.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `tests/test_orchestrator/test_sse_sequence.py`
- Create: `tests/test_agents/test_cover_letter_tone.py`

- [ ] **Step 1: Write the failing test for tone injection**

```python
# tests/test_agents/test_cover_letter_tone.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.cover_letter import CoverLetterAgent
from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)


@pytest.fixture
def prior():
    return PriorOutputs(
        job_parser=JobParserOutput(
            required_skills=["Python"], nice_to_have=[], role_type="SWE", seniority="Mid"
        ),
        match_scorer=MatchScorerOutput(
            score=70, matched_skills=["Python"], missing_skills=[], partial_matches=[]
        ),
        gap_analyst=GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[]),
    )


async def test_tone_injected_into_prompt(prior):
    """The tone value must appear in the system prompt passed to Claude."""
    captured_system: list[str] = []

    async def fake_call(system: str, user: str) -> str:
        captured_system.append(system)
        return '{"subject": "CL", "body": "Dear...", "tone_notes": "direct"}'

    agent = CoverLetterAgent()
    agent._call = fake_call  # type: ignore[method-assign]

    await agent.run("profile text", "job description text", prior, tone="direct")

    assert captured_system, "agent._call was never invoked"
    assert "direct" in captured_system[0].lower()


async def test_default_tone_is_professional(prior):
    """When tone is omitted, it defaults to 'professional'."""
    captured_system: list[str] = []

    async def fake_call(system: str, user: str) -> str:
        captured_system.append(system)
        return '{"subject": "CL", "body": "Dear...", "tone_notes": "formal"}'

    agent = CoverLetterAgent()
    agent._call = fake_call  # type: ignore[method-assign]

    await agent.run("profile text", "job description", prior)

    assert "professional" in captured_system[0].lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_agents/test_cover_letter_tone.py -v
```
Expected: FAIL — `CoverLetterAgent.run` has no `tone` parameter

- [ ] **Step 3: Update `backend/prompts/cover_letter.md` to add `{tone}` slot**

Replace the `## Task` section with:

```markdown
# Cover Letter Writer

You are a professional cover letter writer for software engineers.

## Candidate Profile
{profile}

## Job Requirements
{prior.job_parser}

## Match Analysis
{prior.match_scorer}

## Gap Analysis
{prior.gap_analyst}

## Writing Tone
Write in a {tone} tone.
- professional: formal, measured language; structured paragraphs; confident but not casual
- conversational: warm, human, first-person friendly; write as if speaking directly to the hiring manager
- direct: short sentences, no filler; every sentence earns its place; confident and to the point

## Task
Write a tailored cover letter. Ground everything in the candidate's actual experience — never invent skills, projects, or achievements not in the profile.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"subject": "Cover Letter – [role] at [company or 'Your Company']", "body": "3-4 paragraph letter", "tone_notes": "brief note on tone choices"}
```

- [ ] **Step 4: Update `_inject` in `backend/agents/base.py` to accept `**extras`**

Change the signature and add extra-slot replacement:

```python
def _inject(self, template: str, profile: str, jd: str, prior: PriorOutputs, **extras: str) -> str:
    result = template.replace("{profile}", profile).replace("{jd}", jd)
    for field, value in prior.model_dump(exclude_none=True).items():
        result = result.replace(f"{{prior.{field}}}", json.dumps(value, indent=2))
    for key, value in extras.items():
        result = result.replace(f"{{{key}}}", value)
    return result
```

- [ ] **Step 5: Update `CoverLetterAgent.run` in `backend/agents/cover_letter.py`**

```python
class CoverLetterAgent(BaseAgent):
    async def run(
        self, profile: str, jd: str, prior: PriorOutputs, tone: str = "professional"
    ) -> CoverLetterOutput:
        template = self._load_prompt("cover_letter")
        system = self._inject(template, profile, jd, prior, tone=tone)
        raw = await self._call(system, jd)
        try:
            return CoverLetterOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cover_letter: {e}") from e
```

- [ ] **Step 6: Run tone tests to confirm they pass**

```bash
pytest tests/test_agents/test_cover_letter_tone.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Add `GenerateRequest` to `backend/schemas.py`**

Add after `AnalyseRequest`:

```python
class GenerateRequest(BaseModel):
    tone: str = "professional"
```

- [ ] **Step 8: Update `run_generate_pipeline` in `backend/services/orchestrator.py` to accept `tone`**

Change the function signature:

```python
async def run_generate_pipeline(
    analysis_id: str, tone: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
```

Change the `CoverLetterAgent().run(...)` call:

```python
    cl_result, rt_result = await asyncio.gather(
        CoverLetterAgent().run(full, analysis.jd_text, prior, tone=tone),
        ResumeTailorerAgent().run(full, analysis.jd_text, prior),
        return_exceptions=True,
    )
```

- [ ] **Step 9: Update `backend/routes/analyse.py` to read `GenerateRequest` body**

Update imports to include `GenerateRequest`:

```python
from backend.schemas import AnalyseRequest, GenerateRequest
```

Update `_generate_stream` and `generate_analysis`:

```python
async def _generate_stream(analysis_id: str, tone: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_generate_pipeline(analysis_id, tone, db):
        yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"


@router.post("/analyse/generate/{analysis_id}")
async def generate_analysis(
    analysis_id: str,
    request: GenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _generate_stream(analysis_id, request.tone, db),
        media_type="text/event-stream",
        headers=headers,
    )
```

- [ ] **Step 10: Fix the existing `test_sse_sequence.py` to match the new signature**

In `tests/test_orchestrator/test_sse_sequence.py`, find the line (around line 138):

```python
        async for event in run_generate_pipeline(analysis.id, session):
```

Change to:

```python
        async for event in run_generate_pipeline(analysis.id, "professional", session):
```

- [ ] **Step 11: Run the orchestrator tests to confirm nothing is broken**

```bash
pytest tests/test_orchestrator/ -v
```
Expected: all PASSED

---

## Task 7: Cover Letter Tone Picker (Frontend)

**Context:** Add a tone dropdown to the evaluated phase in `AnalyseJob.tsx` (where the score and "Generate Documents" button appear), and add the same dropdown to the generate banner in `Results.tsx`. Both pages must pass the chosen tone to `streamGenerate`.

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AnalyseJob.tsx`
- Modify: `frontend/src/pages/Results.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add `Tone` type to `frontend/src/types/index.ts`**

Append:

```typescript
export type Tone = "professional" | "conversational" | "direct";
```

- [ ] **Step 2: Update `streamGenerate` in `frontend/src/api/client.ts` to accept `tone`**

Update the import line at top to add `Tone`:

```typescript
import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks, GapsInsightResponse, Tone } from "../types";
```

Change the `streamGenerate` export:

```typescript
export function streamGenerate(analysisId: string, tone: Tone, callbacks: SSECallbacks): () => void {
  return _streamSSE(
    `${BASE}/analyse/generate/${analysisId}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tone }) },
    callbacks,
  );
}
```

- [ ] **Step 3: Update `frontend/src/pages/AnalyseJob.tsx` to add tone state and dropdown**

Add `Tone` to the import:

```tsx
import type { AgentName, AgentStatus, PipelineDoneData, Tone } from "../types";
```

Add tone state inside the component (after the existing `useState` declarations):

```tsx
const [tone, setTone] = useState<Tone>("professional");
```

Pass `tone` to `streamGenerate` in the `generate` function:

```tsx
  const generate = () => {
    if (!evalResult) return;
    setPhase("generating");
    setError(null);
    setStates((p) => ({ ...p, resource_planner: "pending", cover_letter: "pending", resume_tailorer: "pending" }));
    cancelRef.current = streamGenerate(evalResult.analysis_id, tone, {
      onAgentStart: ({ agent }) => setStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: ({ analysis_id }) => navigate(`/results/${analysis_id}`),
    });
  };
```

Replace the `phase === "evaluated"` block with (add tone dropdown before the Generate button):

```tsx
      {phase === "evaluated" && evalResult && (
        <div className="flex items-center gap-4 flex-wrap">
          <div className="text-2xl font-bold text-slate-900">
            {evalResult.score}
            <span className="text-base font-normal text-slate-500">/100</span>
          </div>
          <select
            value={tone}
            onChange={(e) => setTone(e.target.value as Tone)}
            className="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white"
          >
            <option value="professional">Professional</option>
            <option value="conversational">Conversational</option>
            <option value="direct">Direct</option>
          </select>
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
```

- [ ] **Step 4: Update `frontend/src/pages/Results.tsx` to add tone picker in the generate banner**

Add `Tone` to imports:

```tsx
import type { AnalysisDetail, AgentName, AgentStatus, Tone } from "../types";
```

Add tone state inside the component (after the existing `useState` declarations):

```tsx
  const [tone, setTone] = useState<Tone>("professional");
```

Pass `tone` to `streamGenerate` in the `generate` function:

```tsx
  const generate = () => {
    if (!data) return;
    setGenerating(true);
    setGenStates(Object.fromEntries(PHASE2_AGENTS.map((a) => [a, "pending"])));
    cancelRef.current = streamGenerate(data.id, tone, {
      onAgentStart: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "running" })),
      onAgentDone: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "done" })),
      onPipelineError: ({ agent }) => setGenStates((p) => ({ ...p, [agent]: "error" })),
      onPipelineDone: () => {
        api.getAnalysis(data.id).then(setData).finally(() => setGenerating(false));
      },
    });
  };
```

Replace the generate banner block (the `data.evaluate_only && !generating` div) with:

```tsx
      {data.evaluate_only && !generating && (
        <div className="flex items-center gap-3 flex-wrap p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800 flex-1">
            Evaluation complete. Generate your cover letter, resource plan, and resume bullets.
          </p>
          <select
            value={tone}
            onChange={(e) => setTone(e.target.value as Tone)}
            className="px-3 py-1.5 text-sm rounded-lg border border-blue-300 bg-white"
          >
            <option value="professional">Professional</option>
            <option value="conversational">Conversational</option>
            <option value="direct">Direct</option>
          </select>
          <button
            onClick={generate}
            className="shrink-0 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            Generate Documents
          </button>
        </div>
      )}
```

---

## Task 8: Profile Compression via LLM Summary

**Context:** Currently Phase 1 agents (`job_parser`, `match_scorer`) receive a template-based compact profile (YAML + 500 chars of CV). We upgrade this to a Haiku-generated 300-word structured summary stored on the `Profile` row. On new profile builds, `build_profile()` calls Haiku once to generate the summary. `run_evaluate_pipeline` uses `profile.profile_summary` when non-empty; falls back to `build_compact_profile()` for old profiles.

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/services/profile_builder.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `scripts/migrate.py`
- Create: `tests/test_services/test_profile_summary.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services/test_profile_summary.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Profile


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_summarise_profile_returns_text():
    """_summarise_profile calls Haiku and returns the text."""
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="Alice is a Senior Python developer.")]

    with patch("backend.services.profile_builder.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=fake_message)

        from backend.services.profile_builder import _summarise_profile
        result = await _summarise_profile("name: Alice\n", "CV text here.")

    assert result == "Alice is a Senior Python developer."


async def test_summarise_profile_returns_empty_on_error():
    """_summarise_profile returns empty string when Haiku fails; never raises."""
    with patch("backend.services.profile_builder.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        from backend.services.profile_builder import _summarise_profile
        result = await _summarise_profile("name: Alice\n", "CV text here.")

    assert result == ""


async def test_build_profile_stores_summary(session):
    """build_profile() calls _summarise_profile and stores the result."""
    yaml_text = "name: Alice\nskills:\n  - Python\n"
    cv_text = "Alice is a Python developer with 5 years experience."

    with (
        patch("backend.services.profile_builder._read_repos", return_value=(yaml_text, [])),
        patch(
            "backend.services.profile_builder.extract_text_from_file",
            new_callable=AsyncMock,
            return_value=cv_text,
        ),
        patch(
            "backend.services.profile_builder._summarise_profile",
            new_callable=AsyncMock,
            return_value="Alice is a Senior Python developer.",
        ),
    ):
        from backend.services.profile_builder import build_profile
        profile = await build_profile(session)

    assert profile.profile_summary == "Alice is a Senior Python developer."


async def test_evaluate_pipeline_uses_summary_not_compact(session):
    """When profile.profile_summary is non-empty, early agents receive it, not the compact template."""
    from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput

    profile = Profile(
        id="p1",
        yaml_data="name: Alice\n",
        cv_text="Some CV.",
        github_data="{}",
        merged_profile="full profile",
        profile_summary="This is the LLM summary.",
        last_refreshed_at=datetime.now(timezone.utc),
    )

    jp = JobParserOutput(required_skills=[], nice_to_have=[], role_type="SWE", seniority="Mid")
    ms = MatchScorerOutput(score=70, matched_skills=[], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch("backend.services.orchestrator.get_or_build_profile", new_callable=AsyncMock, return_value=profile),
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp) as mock_jp,
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import run_evaluate_pipeline
        async for _ in run_evaluate_pipeline("Python developer role. " * 5, session):
            pass

    # When patching a class method, mock receives args without `self`.
    # call_args[0][0] is the first positional arg: `profile` (the compact string).
    call_profile = mock_jp.call_args[0][0]
    assert call_profile == "This is the LLM summary."
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_services/test_profile_summary.py -v
```
Expected: FAIL — `Profile` has no attribute `profile_summary`

- [ ] **Step 3: Add `profile_summary` to `Profile` in `backend/models.py`**

```python
class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    yaml_data: Mapped[str] = mapped_column(Text)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    github_data: Mapped[str] = mapped_column(Text, default="{}")
    merged_profile: Mapped[str] = mapped_column(Text, default="")
    profile_summary: Mapped[str] = mapped_column(Text, default="")
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    github_last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
```

- [ ] **Step 4: Add `_summarise_profile` and update `build_profile` in `backend/services/profile_builder.py`**

Add `import anthropic` near the top (after existing imports):

```python
import anthropic
```

Add `_HAIKU = "claude-haiku-4-5-20251001"` as a module constant after the `logger` line:

```python
_HAIKU = "claude-haiku-4-5-20251001"
```

Add the `_summarise_profile` async function after `build_compact_profile`:

```python
async def _summarise_profile(yaml_text: str, cv_text: str) -> str:
    """Call Haiku once to produce a concise 300-word structured profile summary.

    Returns empty string if the API call fails so build_profile() can continue.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = (
        "Produce a concise 300-word structured summary of this candidate covering: "
        "name, years of experience, top technical skills, seniority level, and most notable projects. "
        "Be factual — only include information explicitly present in the input. "
        "Plain text only, no markdown.\n\n"
        f"## YAML Profile\n{yaml_text}\n\n"
        f"## CV Excerpt\n{cv_text[:1000]}"
    )
    try:
        msg = await client.messages.create(
            model=_HAIKU,
            max_tokens=512,
            system="You are a profile summarisation assistant. Respond with plain text only.",
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        logger.warning("profile summary generation failed; continuing without summary")
        return ""
```

Update `build_profile` to call `_summarise_profile` and store the result. Replace the block that constructs `Profile(...)`:

```python
    merged = _assemble_merged(yaml_text, cv_text, github_readmes)
    summary = await _summarise_profile(yaml_text, cv_text)

    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        github_data=json.dumps(github_readmes),
        merged_profile=merged,
        profile_summary=summary,
        last_refreshed_at=datetime.now(timezone.utc),
        github_last_fetched_at=max_fetched,
    )
```

- [ ] **Step 5: Update `run_evaluate_pipeline` in `backend/services/orchestrator.py` to use `profile_summary`**

Change the `compact = ...` line (after the cache check, before `yield SSEEvent("pipeline_start", ...)`):

```python
    compact = (
        profile.profile_summary
        if profile.profile_summary
        else build_compact_profile(profile.yaml_data, profile.cv_text)
    )
```

- [ ] **Step 6: Add migration step to `scripts/migrate.py`**

Add after the `status` step, before `conn.commit()`:

```python
    # 6. Add profile_summary to profiles (DEFAULT '' for existing rows)
    try:
        cur.execute("ALTER TABLE profiles ADD COLUMN profile_summary TEXT NOT NULL DEFAULT ''")
        print("✓ Added profile_summary to profiles")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- profile_summary already exists, skipping")
        else:
            raise
```

- [ ] **Step 7: Run the profile summary tests**

```bash
pytest tests/test_services/test_profile_summary.py -v
```
Expected: 4 PASSED

- [ ] **Step 8: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_services/test_profile_builder.py --ignore=tests/test_routes/test_profile.py
```
Expected: all PASSED

---

## Final Migration Script State

After all tasks, `scripts/migrate.py` should have 6 idempotent steps:

1. `github_last_fetched_at` on profiles
2. Create `github_cache` table
3. `evaluate_only` on analyses
4. `jd_hash` on analyses
5. `status` on analyses
6. `profile_summary` on profiles

Run `python scripts/migrate.py` once after implementing all tasks to bring existing `data/jobfit.db` in sync.
