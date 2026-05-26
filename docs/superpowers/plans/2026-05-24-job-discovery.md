# Job Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically fetch jobs from HN's "Who is Hiring?" thread, run them through a 3-stage filter funnel, score matches with the existing Phase 1 pipeline, and surface good matches in a new Discover page — without touching the existing manual analyse flow.

**Architecture:** A new `discovery` service owns fetch → filter → score. Routes are thin triggers. `asyncio.create_task` fires the background task; the frontend polls `GET /api/discovery/runs/{id}` every 3 s. The existing Phase 1 pipeline is extracted into a reusable `_run_phase1` function called by both the SSE wrapper and the discovery background task.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.0 async · SQLite · httpx · Anthropic SDK (Haiku for Stage 2) · React 18 · TypeScript · Tailwind CSS v4

> **Important constraint:** Do NOT run `git commit` — user commits manually. Do NOT run `make run` or `uvicorn` — user starts the server.

---

## File Structure

**Created:**
- `backend/services/hn_client.py` — Algolia HN API fetcher, returns `list[RawJob]`
- `backend/services/discovery.py` — funnel orchestration: `run_discovery`, `_run_discovery_task`, `_process_job`, stages 1+2
- `backend/routes/discovery.py` — 4 thin route handlers
- `frontend/src/pages/Discover.tsx` — Discover page (idle → running → feed states)
- `tests/test_services/test_hn_client.py` — mocked httpx tests
- `tests/test_services/test_discovery.py` — stage 1 filter + process_job tests
- `tests/test_routes/test_discovery_routes.py` — route endpoint tests

**Modified:**
- `backend/models.py` — add `DiscoveryRun`, `Job` tables; add `job_id` nullable FK to `Analysis`
- `backend/services/orchestrator.py` — add `Phase1Result` dataclass + `_run_phase1` function
- `backend/schemas.py` — add `FunnelMetrics`, `DiscoveryRunResponse`, `DiscoveryFeedItem`, `DiscoveryFeedResponse`
- `backend/main.py` — register discovery router; reset stale runs on startup
- `scripts/migrate.py` — add steps 7, 8, 9 for new tables + `job_id` column
- `frontend/src/types/index.ts` — add discovery types
- `frontend/src/api/client.ts` — add 4 discovery API methods
- `frontend/src/App.tsx` — add `/discover` route + nav link

---

## Task 1: DB Models + Migration

**Files:**
- Modify: `backend/models.py`
- Modify: `scripts/migrate.py`
- Test: `tests/test_database.py` (extend existing)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_database.py` (or create new file `tests/test_models_discovery.py`):

```python
# tests/test_models_discovery.py
from __future__ import annotations

import backend.models  # noqa: F401
from backend.database import Base


async def test_new_tables_registered():
    """DiscoveryRun and Job tables exist in metadata."""
    table_names = set(Base.metadata.tables.keys())
    assert "discovery_runs" in table_names
    assert "jobs" in table_names


async def test_analysis_has_job_id_column():
    """Analysis table has job_id column."""
    cols = {c.name for c in Base.metadata.tables["analyses"].columns}
    assert "job_id" in cols


async def test_job_has_globally_unique_dedup_hash():
    """jobs.dedup_hash has a unique constraint."""
    table = Base.metadata.tables["jobs"]
    unique_cols = {
        col.name
        for constraint in table.constraints
        for col in getattr(constraint, "columns", [])
        if hasattr(constraint, "unique") and constraint.unique
    }
    # UniqueConstraint or unique=True on column
    job_cols = {c.name for c in table.columns if getattr(c, "unique", False)}
    assert "dedup_hash" in unique_cols or "dedup_hash" in job_cols
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python -m pytest tests/test_models_discovery.py -v --no-cov
```

Expected: `FAILED` — `discovery_runs not in table_names`

- [ ] **Step 3: Add DiscoveryRun and Job models to models.py**

Replace the full `backend/models.py` with:

```python
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    yaml_data: Mapped[str] = mapped_column(Text)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    github_data: Mapped[str] = mapped_column(Text, default="{}")
    merged_profile: Mapped[str] = mapped_column(Text, default="")
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    github_last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class GithubCache(Base):
    __tablename__ = "github_cache"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner: Mapped[str] = mapped_column(String, nullable=False)
    repo_name: Mapped[str] = mapped_column(String, nullable=False)
    readme_content: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_modified: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    __table_args__ = (UniqueConstraint("owner", "repo_name", name="uq_github_cache_repo"),)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String)
    triggered_by: Mapped[str] = mapped_column(String, default="manual")
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_passed_stage1: Mapped[int] = mapped_column(Integer, default=0)
    jobs_passed_stage2: Mapped[int] = mapped_column(Integer, default=0)
    jobs_scored: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    sources: Mapped[str] = mapped_column(Text, default='[]')
    source_id: Mapped[str] = mapped_column(String, default="")
    source_url: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    company: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    raw_text: Mapped[str] = mapped_column(Text)
    dedup_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    state: Mapped[str] = mapped_column(String, default="discovered")
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    matched_profiles: Mapped[str] = mapped_column(Text, default='[]')
    discovery_run_id: Mapped[str] = mapped_column(String, ForeignKey("discovery_runs.id"))


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
    job_id: Mapped[str | None] = mapped_column(String, ForeignKey("jobs.id"), nullable=True, default=None)
    results: Mapped[list[JobResult]] = relationship("JobResult", back_populates="analysis")


class JobResult(Base):
    __tablename__ = "job_results"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"))
    agent_name: Mapped[str] = mapped_column(String)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[Analysis] = relationship("Analysis", back_populates="results")
```

- [ ] **Step 4: Add migration steps to scripts/migrate.py**

Append inside the `main()` function before `conn.commit()`:

```python
    # 7. Create discovery_runs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id           TEXT PRIMARY KEY,
            source       TEXT NOT NULL,
            triggered_by TEXT NOT NULL DEFAULT 'manual',
            status       TEXT NOT NULL DEFAULT 'pending',
            started_at   TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            jobs_found          INTEGER NOT NULL DEFAULT 0,
            jobs_passed_stage1  INTEGER NOT NULL DEFAULT 0,
            jobs_passed_stage2  INTEGER NOT NULL DEFAULT 0,
            jobs_scored         INTEGER NOT NULL DEFAULT 0
        )
    """)
    print("✓ discovery_runs table ready")

    # 8. Create jobs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id               TEXT PRIMARY KEY,
            sources          TEXT NOT NULL DEFAULT '[]',
            source_id        TEXT NOT NULL DEFAULT '',
            source_url       TEXT NOT NULL DEFAULT '',
            title            TEXT NOT NULL DEFAULT '',
            company          TEXT NOT NULL DEFAULT '',
            location         TEXT,
            raw_text         TEXT NOT NULL,
            dedup_hash       TEXT NOT NULL UNIQUE,
            discovered_at    TIMESTAMP NOT NULL,
            state            TEXT NOT NULL DEFAULT 'discovered',
            relevance_score  INTEGER,
            matched_profiles TEXT NOT NULL DEFAULT '[]',
            discovery_run_id TEXT NOT NULL REFERENCES discovery_runs(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_jobs_dedup_hash ON jobs (dedup_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_jobs_state ON jobs (state)")
    print("✓ jobs table ready")

    # 9. Add job_id to analyses
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN job_id TEXT REFERENCES jobs(id)")
        print("✓ Added job_id to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- job_id already exists, skipping")
        else:
            raise
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_models_discovery.py -v --no-cov
```

Expected: `3 passed`

---

## Task 2: Extract `_run_phase1` from Orchestrator

**Files:**
- Modify: `backend/services/orchestrator.py`
- Create: `tests/test_orchestrator/test_phase1_direct.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator/test_phase1_direct.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, Profile
from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput

JD = "Senior Python Backend Engineer, 5+ years required, remote. " * 4


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_run_phase1_creates_analysis_with_no_job_id(session):
    """_run_phase1 with no job_id creates Analysis(job_id=None)."""
    profile = Profile(
        id="p-test",
        yaml_data="name: Test",
        cv_text="",
        github_data="{}",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.commit()

    jp = JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior")
    ms = MatchScorerOutput(score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import _run_phase1
        result = await _run_phase1(JD, profile, session)

    assert result.score == 82
    assert result.analysis_id is not None
    from sqlalchemy import select
    analysis = (await session.execute(select(Analysis).where(Analysis.id == result.analysis_id))).scalar_one()
    assert analysis.job_id is None
    assert analysis.evaluate_only is True


async def test_run_phase1_sets_job_id_when_provided(session):
    """_run_phase1 with job_id sets Analysis.job_id correctly."""
    from backend.models import DiscoveryRun, Job
    profile = Profile(
        id="p-test2",
        yaml_data="name: Test",
        cv_text="",
        github_data="{}",
        merged_profile="merged",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    session.add(profile)
    session.add(run)
    await session.flush()

    job = Job(
        sources='["hn"]',
        raw_text=JD,
        dedup_hash="abc123",
        discovery_run_id=run.id,
    )
    session.add(job)
    await session.commit()

    jp = JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="Backend", seniority="Senior")
    ms = MatchScorerOutput(score=75, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])

    with (
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
    ):
        from backend.services.orchestrator import _run_phase1
        result = await _run_phase1(JD, profile, session, job_id=job.id)

    from sqlalchemy import select
    analysis = (await session.execute(
        select(Analysis).where(Analysis.id == result.analysis_id)
    )).scalar_one()
    assert analysis.job_id == job.id
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_orchestrator/test_phase1_direct.py -v --no-cov
```

Expected: `ImportError: cannot import name '_run_phase1' from 'backend.services.orchestrator'`

- [ ] **Step 3: Add Phase1Result and _run_phase1 to orchestrator.py**

At the top of `backend/services/orchestrator.py`, add `Phase1Result` dataclass after the existing `SSEEvent` dataclass:

```python
@dataclass
class Phase1Result:
    analysis_id: str
    score: int
    partial: bool
    prior: PriorOutputs
```

Then add the `_run_phase1` function after the `_AgentProtocol` Protocol definition (before `run_evaluate_pipeline`):

```python
async def _run_phase1(
    jd: str,
    profile: Profile,
    db: AsyncSession,
    job_id: str | None = None,
) -> Phase1Result:
    """Run job_parser → match_scorer → gap_analyst. Save Analysis + JobResult rows.

    No SSE. Called by discovery background task and (optionally) by the SSE wrapper.
    job_id is set when called from discovery; None for manual-paste analyses.
    """
    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1_agents: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    for agent_name, agent, profile_str in phase1_agents:
        try:
            output = await agent.run(profile_str, jd, prior)
            prior = prior.model_copy(update={agent_name: output})
            results[agent_name] = output.model_dump()
        except AgentError:
            partial = True

    score = results.get("match_scorer", {}).get("score", 0)
    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()
    analysis = Analysis(
        jd_text=jd,
        profile_id=profile.id,
        partial=partial,
        evaluate_only=True,
        jd_hash=jd_hash,
        job_id=job_id,
    )
    db.add(analysis)
    await db.flush()

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

The existing `run_evaluate_pipeline` does NOT need to change — it still has its own agent loop for SSE streaming and already creates `Analysis(job_id=None)` implicitly via the `default=None` on the model field.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_orchestrator/test_phase1_direct.py tests/test_orchestrator/test_analysis_caching.py -v --no-cov
```

Expected: `4 passed` (2 new + existing 3 caching tests, minus any that were already failing)

---

## Task 3: HN Client

**Files:**
- Create: `backend/services/hn_client.py`
- Create: `tests/test_services/test_hn_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_hn_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


async def test_strip_html_removes_tags_and_decodes_entities():
    from backend.services.hn_client import _strip_html
    result = _strip_html("<p>We&#39;re hiring a <b>Python</b> engineer.</p>")
    assert "<" not in result
    assert "Python" in result
    assert "We're" in result


async def test_fetch_hn_jobs_returns_empty_when_no_thread():
    """Returns [] when Algolia finds no thread this month."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"hits": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from backend.services.hn_client import fetch_hn_jobs
        jobs = await fetch_hn_jobs()

    assert jobs == []


async def test_fetch_hn_jobs_skips_short_comments():
    """Comments shorter than 100 chars are skipped."""
    thread_resp = MagicMock()
    thread_resp.raise_for_status = MagicMock()
    thread_resp.json = MagicMock(return_value={"hits": [{"objectID": "111"}]})

    comments_resp = MagicMock()
    comments_resp.raise_for_status = MagicMock()
    comments_resp.json = MagicMock(return_value={
        "hits": [
            {"objectID": "222", "comment_text": "<p>Short</p>"},
            {"objectID": "333", "comment_text": "<p>" + "We are hiring a Python engineer with 5+ years experience. " * 5 + "</p>"},
        ],
        "nbPages": 1,
    })

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url, params=None):
        nonlocal call_count
        call_count += 1
        return thread_resp if call_count == 1 else comments_resp

    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        from backend.services import hn_client
        import importlib
        importlib.reload(hn_client)
        jobs = await hn_client.fetch_hn_jobs()

    assert len(jobs) == 1
    assert jobs[0].source_id == "333"


async def test_raw_job_has_correct_fields():
    """RawJob.dedup_hash is sha256 of raw_text."""
    import hashlib
    from backend.services.hn_client import RawJob
    text = "some job text here"
    job = RawJob(
        source_id="x",
        source_url="https://news.ycombinator.com/item?id=x",
        raw_text=text,
        dedup_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    assert len(job.dedup_hash) == 64
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_services/test_hn_client.py -v --no-cov
```

Expected: `ModuleNotFoundError: No module named 'backend.services.hn_client'`

- [ ] **Step 3: Create backend/services/hn_client.py**

```python
# backend/services/hn_client.py
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

HN_ALGOLIA = "https://hn.algolia.com/api/v1"
_MIN_TEXT_LEN = 100


@dataclass
class RawJob:
    source_id: str
    source_url: str
    raw_text: str
    dedup_hash: str


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _month_start_ts() -> int:
    now = datetime.now(timezone.utc)
    return int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())


async def _find_thread_id() -> str | None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{HN_ALGOLIA}/search",
            params={
                "query": "Ask HN: Who is hiring?",
                "tags": "story",
                "numericFilters": f"created_at_i>{_month_start_ts()}",
            },
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        return str(hits[0]["objectID"]) if hits else None


async def fetch_hn_jobs() -> list[RawJob]:
    """Fetch all top-level comments from the current month's HN hiring thread."""
    thread_id = await _find_thread_id()
    if thread_id is None:
        return []

    jobs: list[RawJob] = []
    page = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(
                f"{HN_ALGOLIA}/search",
                params={
                    "tags": f"comment,story_{thread_id}",
                    "hitsPerPage": 200,
                    "page": page,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                break
            for hit in hits:
                raw_html = hit.get("comment_text", "")
                if not raw_html:
                    continue
                text = _strip_html(raw_html)
                if len(text) < _MIN_TEXT_LEN:
                    continue
                obj_id = str(hit["objectID"])
                jobs.append(RawJob(
                    source_id=obj_id,
                    source_url=f"https://news.ycombinator.com/item?id={obj_id}",
                    raw_text=text,
                    dedup_hash=hashlib.sha256(text.encode()).hexdigest(),
                ))
            if page >= data.get("nbPages", 1) - 1:
                break
            page += 1

    return jobs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_services/test_hn_client.py -v --no-cov
```

Expected: `4 passed`

---

## Task 4: Discovery Service

**Files:**
- Create: `backend/services/discovery.py`
- Create: `tests/test_services/test_discovery.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services/test_discovery.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import DiscoveryRun, Job, Profile
from backend.services.hn_client import RawJob


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def test_stage1_pass_matches_target_role():
    from backend.services.discovery import SearchProfile, _stage1_pass
    profiles = [SearchProfile(name="Test", target_roles=["Backend Engineer"], min_score=60)]
    assert _stage1_pass("We are hiring a Backend Engineer with Python skills.", profiles) is True


async def test_stage1_pass_rejects_irrelevant_text():
    from backend.services.discovery import SearchProfile, _stage1_pass
    profiles = [SearchProfile(name="Test", target_roles=["Backend Engineer", "ML Engineer"], min_score=60)]
    assert _stage1_pass("Sales manager wanted for EMEA region expansion.", profiles) is False


async def test_stage1_pass_uses_union_of_all_profiles():
    from backend.services.discovery import SearchProfile, _stage1_pass
    profiles = [
        SearchProfile(name="AI", target_roles=["ML Engineer"], min_score=65),
        SearchProfile(name="Broad", target_roles=["DevOps"], min_score=50),
    ]
    # "DevOps" only in the Broad profile — still passes because union is used
    assert _stage1_pass("DevOps Engineer needed for infra team.", profiles) is True


async def test_process_job_filters_stage1_failure(session):
    """Job is created and state=filtered when Stage 1 fails."""
    from backend.services.discovery import SearchProfile, _process_job

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p1", yaml_data="x", cv_text="", github_data="{}", merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.commit()

    raw = RawJob(source_id="1", source_url="https://hn.com/1", raw_text="Sales manager wanted " * 10, dedup_hash="hash1")
    profiles = [SearchProfile(name="AI", target_roles=["Backend Engineer"], min_score=65)]

    await _process_job(session, run.id, raw, profiles, profile, "compact profile text")

    job = (await session.execute(select(Job).where(Job.dedup_hash == "hash1"))).scalar_one()
    assert job.state == "filtered"
    assert job.relevance_score is None


async def test_process_job_skips_duplicate_hash(session):
    """Duplicate dedup_hash appends source instead of creating a new row."""
    from backend.services.discovery import SearchProfile, _process_job

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p2", yaml_data="x", cv_text="", github_data="{}", merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.flush()

    # Pre-existing job with the same hash
    existing_job = Job(
        sources='["watchlist"]', source_id="old", source_url="https://company.com/job",
        raw_text="Python backend engineer " * 10,
        dedup_hash="same-hash-xyz",
        discovery_run_id=run.id,
        state="scored",
    )
    session.add(existing_job)
    await session.commit()

    raw = RawJob(source_id="99", source_url="https://hn.com/99",
                 raw_text="Python backend engineer " * 10, dedup_hash="same-hash-xyz")
    profiles = [SearchProfile(name="AI", target_roles=["Backend"], min_score=65)]

    await _process_job(session, run.id, raw, profiles, profile, "compact")

    # Only one job row with this hash
    jobs = (await session.execute(select(Job).where(Job.dedup_hash == "same-hash-xyz"))).scalars().all()
    assert len(jobs) == 1
    import json
    sources = json.loads(jobs[0].sources)
    assert "hn" in sources


async def test_process_job_scores_relevant_job(session):
    """Job reaching Phase 1 gets relevance_score set and state=scored."""
    from backend.services.discovery import SearchProfile, Stage2Result, _process_job
    from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput
    from backend.services.orchestrator import Phase1Result
    from backend.schemas import PriorOutputs

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(
        id="p3", yaml_data="x", cv_text="", github_data="{}", merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.add(profile)
    await session.commit()

    raw = RawJob(
        source_id="55", source_url="https://hn.com/55",
        raw_text="Backend Engineer Python FastAPI AWS " * 8,
        dedup_hash="hash-relevant",
    )
    profiles = [SearchProfile(name="AI", target_roles=["Backend Engineer"], min_score=65)]

    fake_s2 = Stage2Result(relevant=True, reason="Good fit", title="Backend Engineer", company="Acme", location="Remote")
    fake_phase1 = Phase1Result(analysis_id="a-1", score=78, partial=False, prior=PriorOutputs())

    with (
        patch("backend.services.discovery._stage2_check", new_callable=AsyncMock, return_value=fake_s2),
        patch("backend.services.discovery._run_phase1", new_callable=AsyncMock, return_value=fake_phase1),
    ):
        await _process_job(session, run.id, raw, profiles, profile, "compact")

    job = (await session.execute(select(Job).where(Job.dedup_hash == "hash-relevant"))).scalar_one()
    assert job.state == "scored"
    assert job.relevance_score == 78
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_services/test_discovery.py -v --no-cov
```

Expected: `ModuleNotFoundError: No module named 'backend.services.discovery'`

- [ ] **Step 3: Create backend/services/discovery.py**

```python
# backend/services/discovery.py
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
import yaml
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import HAIKU
from backend.config import settings
from backend.database import SessionLocal
from backend.models import DiscoveryRun, Job
from backend.schemas import PriorOutputs
from backend.services.hn_client import RawJob, fetch_hn_jobs
from backend.services.orchestrator import Phase1Result, _run_phase1
from backend.services.profile_builder import build_compact_profile, get_or_build_profile

logger = logging.getLogger(__name__)


@dataclass
class SearchProfile:
    name: str
    target_roles: list[str]
    min_score: int


@dataclass
class Stage2Result:
    relevant: bool
    reason: str
    title: str
    company: str
    location: str | None


def _load_search_profiles() -> list[SearchProfile]:
    """Read search_profiles from candidate_profile.yaml. Returns [] if missing."""
    try:
        text = Path(settings.profile_yaml_path).read_text()
        data = yaml.safe_load(text)
        return [
            SearchProfile(name=p["name"], target_roles=p["target_roles"], min_score=p["min_score"])
            for p in data.get("search_profiles", [])
        ]
    except Exception:
        return []


def _stage1_pass(raw_text: str, profiles: list[SearchProfile]) -> bool:
    """Zero-cost keyword filter. True if any target_role from any profile appears in text."""
    all_roles = {r.lower() for p in profiles for r in p.target_roles}
    text_lower = raw_text.lower()
    return any(role in text_lower for role in all_roles)


async def _stage2_check(raw_text: str, compact_profile: str) -> Stage2Result:
    """Haiku relevance check. Returns relevance + title/company/location in one call."""
    system = (
        "You are evaluating job postings for a candidate.\n\n"
        f"Candidate summary:\n{compact_profile[:1000]}\n\n"
        "Evaluate if the job posting is relevant to this candidate. "
        'Respond with ONLY valid JSON: {"relevant": true/false, "reason": "one sentence", '
        '"title": "job title or empty string", "company": "company name or empty string", "location": "city/remote or null"}'
    )
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    msg = await client.messages.create(
        model=HAIKU,
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": f"Job posting:\n{raw_text[:3000]}"}],
    )
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    start, end = raw.find("{"), raw.rfind("}") + 1
    data = json.loads(raw[start:end])
    return Stage2Result(
        relevant=bool(data.get("relevant", False)),
        reason=data.get("reason", ""),
        title=data.get("title", ""),
        company=data.get("company", ""),
        location=data.get("location"),
    )


def _match_profiles(score: int, profiles: list[SearchProfile]) -> list[str]:
    return [p.name for p in profiles if score >= p.min_score]


async def _bump_run(db: AsyncSession, run_id: str, field: str) -> None:
    col = getattr(DiscoveryRun, field)
    await db.execute(
        update(DiscoveryRun).where(DiscoveryRun.id == run_id).values({field: col + 1})
    )
    await db.commit()


async def _process_job(
    db: AsyncSession,
    run_id: str,
    raw: RawJob,
    profiles: list[SearchProfile],
    profile: Any,
    compact: str,
) -> None:
    # 1. Dedup check
    existing = (await db.execute(
        select(Job).where(Job.dedup_hash == raw.dedup_hash)
    )).scalar_one_or_none()
    if existing is not None:
        sources = json.loads(existing.sources)
        if "hn" not in sources:
            sources.append("hn")
            await db.execute(
                update(Job).where(Job.id == existing.id).values(sources=json.dumps(sources))
            )
            await db.commit()
        return

    # 2. Create job row, commit immediately so filtered jobs persist
    job = Job(
        sources='["hn"]',
        source_id=raw.source_id,
        source_url=raw.source_url,
        raw_text=raw.raw_text,
        dedup_hash=raw.dedup_hash,
        state="discovered",
        discovery_run_id=run_id,
    )
    db.add(job)
    await db.flush()
    await db.commit()

    # 3. Stage 1: keyword filter (pure Python, zero cost)
    if not _stage1_pass(raw.raw_text, profiles):
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
    await _bump_run(db, run_id, "jobs_passed_stage1")

    # 4. Stage 2: Haiku relevance + metadata extraction
    try:
        s2 = await _stage2_check(raw.raw_text, compact)
    except Exception as e:
        logger.warning("Stage 2 failed for job %s: %s", job.id, e)
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return

    await db.execute(
        update(Job).where(Job.id == job.id).values(
            title=s2.title, company=s2.company, location=s2.location
        )
    )
    await db.commit()

    if not s2.relevant:
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
    await _bump_run(db, run_id, "jobs_passed_stage2")

    # 5. Phase 1: full evaluate pipeline (saves Analysis row with job_id=job.id)
    try:
        result = await _run_phase1(raw.raw_text, profile, db, job_id=job.id)
    except Exception as e:
        logger.warning("Phase 1 failed for job %s: %s", job.id, e)
        return

    matched = _match_profiles(result.score, profiles)
    await db.execute(
        update(Job).where(Job.id == job.id).values(
            relevance_score=result.score,
            matched_profiles=json.dumps(matched),
            state="scored",
        )
    )
    await db.commit()
    await _bump_run(db, run_id, "jobs_scored")


async def _run_discovery_task(run_id: str, source: str) -> None:
    """Background task. Owns its own DB session."""
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(status="running")
        )
        await db.commit()
        try:
            raw_jobs = await fetch_hn_jobs()
            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(jobs_found=len(raw_jobs))
            )
            await db.commit()

            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            compact = build_compact_profile(profile.yaml_data, profile.cv_text)

            for raw in raw_jobs:
                await _process_job(db, run_id, raw, profiles, profile, compact)

            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(
                    status="complete",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        except Exception as e:
            logger.error("Discovery run %s failed: %s", run_id, e, exc_info=True)
            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(
                    status="failed",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()


async def run_discovery(source: str, db: AsyncSession) -> str:
    """Public entry point. Creates DiscoveryRun, fires background task, returns run_id."""
    run = DiscoveryRun(
        source=source,
        triggered_by="manual",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    asyncio.create_task(_run_discovery_task(run.id, source))
    return run.id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_services/test_discovery.py -v --no-cov
```

Expected: `5 passed`

---

## Task 5: Discovery Schemas + Routes + Main Wiring

**Files:**
- Modify: `backend/schemas.py`
- Create: `backend/routes/discovery.py`
- Modify: `backend/main.py`
- Create: `tests/test_routes/test_discovery_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes/test_discovery_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import backend.models  # noqa: F401


async def test_trigger_discovery_returns_run_id(app_client):
    with patch("backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-abc"):
        resp = await app_client.post("/api/discovery/run?source=hn")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-abc"


async def test_get_run_returns_run(app_client, db_session):
    from backend.models import DiscoveryRun
    run = DiscoveryRun(
        id="run-123",
        source="hn",
        triggered_by="manual",
        status="complete",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        jobs_found=100,
        jobs_passed_stage1=20,
        jobs_passed_stage2=10,
        jobs_scored=10,
    )
    db_session.add(run)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/runs/run-123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "run-123"
    assert data["status"] == "complete"
    assert data["funnel"]["jobs_found"] == 100
    assert data["funnel"]["passed_stage1"] == 20
    assert data["funnel"]["passed_stage2"] == 10
    assert data["funnel"]["scored"] == 10


async def test_get_run_not_found_returns_404(app_client):
    resp = await app_client.get("/api/discovery/runs/does-not-exist")
    assert resp.status_code == 404


async def test_list_runs_returns_recent_first(app_client, db_session):
    from backend.models import DiscoveryRun
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    for i, status in enumerate(["complete", "failed", "complete"]):
        db_session.add(DiscoveryRun(
            source="hn", triggered_by="manual", status=status,
            started_at=now + timedelta(minutes=i),
        ))
    await db_session.commit()

    resp = await app_client.get("/api/discovery/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 3
    # Most recent first
    assert runs[0]["started_at"] >= runs[1]["started_at"]


async def test_feed_returns_scored_jobs(app_client, db_session):
    from backend.models import Analysis, DiscoveryRun, Job, Profile
    profile = Profile(
        id="p1", yaml_data="x", cv_text="", github_data="{}", merged_profile="m",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    run = DiscoveryRun(source="hn", status="complete", started_at=datetime.now(timezone.utc))
    db_session.add(profile)
    db_session.add(run)
    await db_session.flush()

    job = Job(
        sources='["hn"]', source_id="1", source_url="https://hn.com/1",
        title="Backend Engineer", company="Acme", location="Remote",
        raw_text="Python backend " * 10, dedup_hash="h1",
        state="scored", relevance_score=80,
        matched_profiles='["AI-focused"]',
        discovery_run_id=run.id,
    )
    db_session.add(job)
    await db_session.flush()

    analysis = Analysis(
        jd_text="Python backend " * 10, profile_id=profile.id,
        evaluate_only=True, jd_hash="jdh1", job_id=job.id,
    )
    db_session.add(analysis)
    await db_session.commit()

    resp = await app_client.get("/api/discovery/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Backend Engineer"
    assert data["items"][0]["relevance_score"] == 80
    assert data["items"][0]["analysis_id"] == analysis.id
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_routes/test_discovery_routes.py -v --no-cov
```

Expected: all fail — routes and schemas don't exist yet

- [ ] **Step 3: Add discovery schemas to backend/schemas.py**

Append to the end of `backend/schemas.py`:

```python
class FunnelMetrics(BaseModel):
    jobs_found: int
    passed_stage1: int
    passed_stage2: int
    scored: int


class DiscoveryRunResponse(BaseModel):
    id: str
    source: str
    triggered_by: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    funnel: FunnelMetrics


class DiscoveryFeedItem(BaseModel):
    id: str
    title: str
    company: str
    location: str | None
    source_url: str
    sources: list[str]
    relevance_score: int
    matched_profiles: list[str]
    analysis_id: str | None
    state: str
    discovered_at: datetime


class DiscoveryFeedResponse(BaseModel):
    items: list[DiscoveryFeedItem]
    total: int
    has_more: bool
```

- [ ] **Step 4: Create backend/routes/discovery.py**

```python
# backend/routes/discovery.py
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Analysis, DiscoveryRun, Job
from backend.schemas import (
    DiscoveryFeedItem,
    DiscoveryFeedResponse,
    DiscoveryRunResponse,
    FunnelMetrics,
)
from backend.services.discovery import run_discovery

router = APIRouter(tags=["discovery"])


def _run_to_response(run: DiscoveryRun) -> DiscoveryRunResponse:
    return DiscoveryRunResponse(
        id=run.id,
        source=run.source,
        triggered_by=run.triggered_by,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        funnel=FunnelMetrics(
            jobs_found=run.jobs_found,
            passed_stage1=run.jobs_passed_stage1,
            passed_stage2=run.jobs_passed_stage2,
            scored=run.jobs_scored,
        ),
    )


@router.post("/discovery/run")
async def trigger_discovery(
    source: str = Query(default="hn"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    run_id = await run_discovery(source, db)
    return {"run_id": run_id}


@router.get("/discovery/runs/{run_id}", response_model=DiscoveryRunResponse)
async def get_discovery_run(run_id: str, db: AsyncSession = Depends(get_db)) -> DiscoveryRunResponse:
    run = (await db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    return _run_to_response(run)


@router.get("/discovery/runs", response_model=list[DiscoveryRunResponse])
async def list_discovery_runs(db: AsyncSession = Depends(get_db)) -> list[DiscoveryRunResponse]:
    runs = (
        await db.execute(
            select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(20)
        )
    ).scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/discovery/feed", response_model=DiscoveryFeedResponse)
async def get_discovery_feed(
    profile: str | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryFeedResponse:
    base = (
        select(Job, Analysis.id.label("analysis_id"))
        .outerjoin(Analysis, Analysis.job_id == Job.id)
        .where(Job.state == "scored")
        .where(Job.relevance_score >= min_score)
    )
    if profile:
        # SQLite JSON contains check via LIKE pattern
        base = base.where(Job.matched_profiles.like(f'%"{profile}"%'))

    total_q = select(func.count()).select_from(base.subquery())
    total: int = (await db.execute(total_q)).scalar_one()

    rows = (
        await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))
    ).all()

    items = [
        DiscoveryFeedItem(
            id=row.Job.id,
            title=row.Job.title,
            company=row.Job.company,
            location=row.Job.location,
            source_url=row.Job.source_url,
            sources=json.loads(row.Job.sources),
            relevance_score=row.Job.relevance_score or 0,
            matched_profiles=json.loads(row.Job.matched_profiles),
            analysis_id=row.analysis_id,
            state=row.Job.state,
            discovered_at=row.Job.discovered_at,
        )
        for row in rows
    ]

    return DiscoveryFeedResponse(items=items, total=total, has_more=offset + limit < total)
```

- [ ] **Step 5: Update backend/main.py — register router + startup reset**

```python
# backend/main.py
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import DiscoveryRun
from backend.routes.analyse import router as analyse_router
from backend.routes.discovery import router as discovery_router
from backend.routes.history import router as history_router
from backend.routes.profile import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    # Reset any discovery runs that were left in "running" state (e.g. server crash)
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.status == "running")
            .values(status="failed", completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
    yield


app = FastAPI(title="JobFit Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router, prefix=settings.api_prefix)
app.include_router(analyse_router, prefix=settings.api_prefix)
app.include_router(history_router, prefix=settings.api_prefix)
app.include_router(discovery_router, prefix=settings.api_prefix)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_routes/test_discovery_routes.py -v --no-cov
```

Expected: `5 passed`

Then run full suite to catch regressions:

```bash
python -m pytest --no-cov -q
```

Expected: all existing tests still pass

---

## Task 6: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

No tests for TypeScript in this project — verify correctness in Task 7 by running the UI.

- [ ] **Step 1: Add discovery types to frontend/src/types/index.ts**

Append to the end of `frontend/src/types/index.ts`:

```typescript
export interface FunnelMetrics {
  jobs_found: number;
  passed_stage1: number;
  passed_stage2: number;
  scored: number;
}

export interface DiscoveryRun {
  id: string;
  source: string;
  triggered_by: string;
  status: "pending" | "running" | "complete" | "failed";
  started_at: string;
  completed_at: string | null;
  funnel: FunnelMetrics;
}

export interface DiscoveryFeedItem {
  id: string;
  title: string;
  company: string;
  location: string | null;
  source_url: string;
  sources: string[];
  relevance_score: number;
  matched_profiles: string[];
  analysis_id: string | null;
  state: string;
  discovered_at: string;
}

export interface DiscoveryFeedResponse {
  items: DiscoveryFeedItem[];
  total: number;
  has_more: boolean;
}
```

- [ ] **Step 2: Add discovery API methods to frontend/src/api/client.ts**

First, update the import line at the top to include the new types:

```typescript
import type {
  ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse,
  AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks,
  DiscoveryRun, DiscoveryFeedResponse,
} from "../types";
```

Then add these methods to the `api` object inside `client.ts` (after `getAnalysis`):

```typescript
  triggerDiscovery: async (source: string): Promise<{ run_id: string }> => {
    const r = await fetch(`${BASE}/discovery/run?source=${source}`, { method: "POST" });
    if (!r.ok) throw new Error(`Trigger discovery failed: ${r.status}`);
    return r.json() as Promise<{ run_id: string }>;
  },
  getDiscoveryRun: (runId: string) => get<DiscoveryRun>(`/discovery/runs/${runId}`),
  getDiscoveryRuns: () => get<DiscoveryRun[]>("/discovery/runs"),
  getDiscoveryFeed: (params: { profile?: string; minScore?: number; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.profile) q.set("profile", params.profile);
    if (params.minScore !== undefined) q.set("min_score", String(params.minScore));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return get<DiscoveryFeedResponse>(`/discovery/feed${qs ? "?" + qs : ""}`);
  },
```

- [ ] **Step 3: Verify TypeScript compiles without errors**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit
```

Expected: no errors

---

## Task 7: Discover Page + App Routing

**Files:**
- Create: `frontend/src/pages/Discover.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/pages/Discover.tsx**

```tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, streamGenerate } from "../api/client";
import type { DiscoveryRun, DiscoveryFeedItem } from "../types";

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? "text-green-700 bg-green-50 border-green-200" :
    score >= 50 ? "text-amber-700 bg-amber-50 border-amber-200" :
                 "text-slate-600 bg-slate-50 border-slate-200";
  return (
    <span className={`text-sm font-bold px-2 py-0.5 rounded border ${color}`}>
      {score}%
    </span>
  );
}

function FunnelBar({ run }: { run: DiscoveryRun }) {
  const f = run.funnel;
  const isRunning = run.status === "running" || run.status === "pending";
  return (
    <div className="p-4 rounded-lg border bg-white">
      <p className="text-sm font-medium text-slate-700 mb-2">
        {isRunning ? "Fetching HN jobs…" :
         run.status === "complete" ? `Completed ${new Date(run.completed_at!).toLocaleString()}` :
         run.status === "failed" ? "Fetch failed — check server logs" :
         "Starting…"}
      </p>
      <div className="flex gap-4 text-xs text-slate-500">
        <span><strong className="text-slate-700">{f.jobs_found}</strong> found</span>
        <span>→ <strong className="text-slate-700">{f.passed_stage1}</strong> keyword</span>
        <span>→ <strong className="text-slate-700">{f.passed_stage2}</strong> relevant</span>
        <span>→ <strong className="text-slate-700">{f.scored}</strong> scored ✓</span>
      </div>
    </div>
  );
}

function JobCard({ job }: { job: DiscoveryFeedItem }) {
  const navigate = useNavigate();
  const [generating, setGenerating] = useState(false);

  function handleGenerate() {
    if (!job.analysis_id) return;
    setGenerating(true);
    streamGenerate(job.analysis_id, {
      onPipelineDone: (data) => {
        setGenerating(false);
        navigate(`/results/${data.analysis_id}`);
      },
      onPipelineError: () => setGenerating(false),
    });
  }

  return (
    <div className="p-4 rounded-lg border bg-white hover:border-slate-300 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <ScoreBadge score={job.relevance_score} />
            <span className="font-medium text-slate-900 truncate">{job.title || "Unknown role"}</span>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">
            {job.company || "Unknown company"}
            {job.location ? ` · ${job.location}` : ""}
          </p>
          {job.matched_profiles.length > 0 && (
            <div className="flex gap-1 mt-2 flex-wrap">
              {job.matched_profiles.map((p) => (
                <span key={p} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-200">
                  {p}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-2 shrink-0 items-center">
          <a
            href={job.source_url || "#"}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 border rounded"
          >
            View ↗
          </a>
          {job.analysis_id && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {generating ? "Generating…" : "Generate docs ↗"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Discover() {
  const [lastRun, setLastRun] = useState<DiscoveryRun | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<DiscoveryRun | null>(null);
  const [feed, setFeed] = useState<DiscoveryFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [profileFilter, setProfileFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFeed = useCallback(async (profile?: string) => {
    const res = await api.getDiscoveryFeed({ profile: profile || undefined });
    setFeed(res.items);
    setTotal(res.total);
  }, []);

  // Load most recent run on mount
  useEffect(() => {
    api.getDiscoveryRuns()
      .then((runs) => {
        if (runs.length > 0) {
          setLastRun(runs[0]);
          if (runs[0].status === "complete") loadFeed();
        }
      })
      .finally(() => setLoading(false));
  }, [loadFeed]);

  // Poll active run
  useEffect(() => {
    if (!activeRunId) return;
    pollRef.current = setInterval(async () => {
      const run = await api.getDiscoveryRun(activeRunId);
      setActiveRun(run);
      if (run.status === "complete" || run.status === "failed") {
        clearInterval(pollRef.current!);
        setActiveRunId(null);
        setFetching(false);
        setLastRun(run);
        if (run.status === "complete") loadFeed(profileFilter || undefined);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeRunId, profileFilter, loadFeed]);

  async function triggerFetch() {
    setFetching(true);
    setActiveRun(null);
    const { run_id } = await api.triggerDiscovery("hn");
    setActiveRunId(run_id);
  }

  function handleProfileFilter(value: string) {
    setProfileFilter(value);
    loadFeed(value || undefined);
  }

  const displayRun = activeRun || lastRun;
  const allProfiles = Array.from(new Set(feed.flatMap((j) => j.matched_profiles)));

  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Discover Jobs</h1>
          {!displayRun && (
            <p className="text-sm text-slate-500 mt-1">Fetch jobs from Hacker News "Who is Hiring?"</p>
          )}
        </div>
        <button
          onClick={triggerFetch}
          disabled={fetching}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {fetching ? "Fetching…" : "Fetch HN Jobs"}
        </button>
      </div>

      {displayRun && <FunnelBar run={displayRun} />}

      {feed.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">{total} scored jobs</p>
            <select
              value={profileFilter}
              onChange={(e) => handleProfileFilter(e.target.value)}
              className="text-sm border rounded-md px-2 py-1 bg-white"
            >
              <option value="">All profiles</option>
              {allProfiles.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="space-y-3">
            {feed.map((job) => <JobCard key={job.id} job={job} />)}
          </div>
        </>
      )}

      {feed.length === 0 && lastRun?.status === "complete" && (
        <p className="text-slate-500 text-sm">
          No scored jobs found. Try adjusting your <code>search_profiles</code> in{" "}
          <code>data/candidate_profile.yaml</code>.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add /discover route and nav link to frontend/src/App.tsx**

```tsx
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { History } from "./pages/History";
import { Discover } from "./pages/Discover";

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
          <NavLink to="/discover" className={link}>Discover</NavLink>
          <NavLink to="/history" className={link}>History</NavLink>
        </nav>
        <main className="py-8">
          <Routes>
            <Route path="/" element={<ProfileSetup />} />
            <Route path="/analyse" element={<AnalyseJob />} />
            <Route path="/results/:id" element={<Results />} />
            <Route path="/discover" element={<Discover />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Run full backend test suite**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python -m pytest -q
```

Expected: all tests pass, coverage ≥ 70%
