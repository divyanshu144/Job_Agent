# JobFit Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade local-first web app that analyses job descriptions against a candidate profile using a 6-agent AI pipeline, returning match score, gap analysis, tailored cover letter, and resume bullets.

**Architecture:** FastAPI backend with async SQLAlchemy (SQLite), 6-agent pipeline using Anthropic SDK (`claude-sonnet-4-6`) in a two-phase execution model (Phase 1 sequential, Phase 2 parallel via `asyncio.gather`), React 18 + Vite + TypeScript frontend consuming per-agent SSE events.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, aiosqlite, Anthropic SDK, httpx, pypdf, PyYAML | React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui, React Router v6

---

## File Map

```
backend/
  __init__.py, config.py, database.py, models.py, schemas.py, main.py
  agents/  __init__.py base.py job_parser.py match_scorer.py gap_analyst.py
           resource_planner.py cover_letter.py resume_tailorer.py
  services/ __init__.py github_client.py cv_parser.py profile_builder.py orchestrator.py
  routes/  __init__.py profile.py analyse.py history.py
  prompts/ job_parser.md match_scorer.md gap_analyst.md
           resource_planner.md cover_letter.md resume_tailorer.md
tests/
  conftest.py
  test_agents/  test_job_parser.py test_match_scorer.py test_gap_analyst.py
                test_resource_planner.py test_cover_letter.py test_resume_tailorer.py
  test_services/ test_github_client.py test_cv_parser.py test_profile_builder.py
  test_orchestrator/ test_sse_sequence.py
  test_routes/ test_profile.py test_analyse.py test_history.py
frontend/src/
  types/index.ts  api/client.ts  App.tsx
  components/ AgentProgress.tsx ScoreCard.tsx GapList.tsx ResourcePanel.tsx DocViewer.tsx
  pages/ ProfileSetup.tsx AnalyseJob.tsx Results.tsx History.tsx
data/ candidate_profile.yaml
scripts/ check_schema_drift.py
requirements.txt  pyproject.toml  Makefile  Dockerfile  docker-compose.yml
.env.example  .gitignore
```

---

## PHASE 1 — FOUNDATION

### Task 1: Project Skeleton & Tooling

**Files:** `requirements.txt`, `pyproject.toml`, `.env.example`, `.gitignore`, `data/candidate_profile.yaml`, all `__init__.py` files

- [ ] **Create `requirements.txt`**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.9.0
pydantic-settings>=2.6.0
sqlalchemy>=2.0.0
aiosqlite>=0.20.0
anthropic>=0.40.0
httpx>=0.27.0
pypdf>=4.0.0
pyyaml>=6.0.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-cov>=5.0.0
httpx[asyncio]>=0.27.0
ruff>=0.7.0
mypy>=1.11.0
types-PyYAML>=6.0.0
```

- [ ] **Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=backend --cov-report=term-missing --cov-fail-under=70"

[tool.ruff]
line-length = 100
select = ["E", "F", "I"]

[tool.mypy]
strict = true
ignore_missing_imports = true
```

- [ ] **Create `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_USERNAME=divyanshu144
DATABASE_URL=sqlite+aiosqlite:///./data/jobfit.db
API_PREFIX=/api
CV_PATH=data/cv.pdf
PROFILE_YAML_PATH=data/candidate_profile.yaml
```

- [ ] **Create `.gitignore`**

```
.env
data/cv.pdf
data/jobfit.db
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
frontend/node_modules/
frontend/dist/
```

- [ ] **Create `data/candidate_profile.yaml`**

```yaml
identity:
  name: Divyanshu Charak
  github_username: divyanshu144
  target_roles: [ML Engineer, Data Scientist, AI/Automation Developer]
  location_preferences: [UK, Remote, Europe]

core_skills:
  languages: [Python, TypeScript, SQL, R]
  ml: [scikit-learn, XGBoost, SHAP, PyTorch]
  llm: [Claude API, OpenAI, RAG, prompt engineering, LangChain]
  web: [FastAPI, React, Next.js, Redux]
  data: [PostgreSQL, SQLite, Redis, pandas, NumPy]
  cloud: ["AWS (ECS, RDS, S3)", Docker, GitHub Actions]

domains:
  - Energy policy analytics
  - Document intelligence (RAG)
  - LLM evaluation & MLOps

featured_projects:
  - repo: divyanshu144/docchat
  - repo: divyanshu144/promptops
  - repo: divyanshu144/epc-south-west

currently_learning:
  - AWS deployment (ECS Fargate)
  - Agentic pipelines
```

- [ ] **Create all `__init__.py` files**

```bash
touch backend/__init__.py backend/agents/__init__.py backend/services/__init__.py \
      backend/routes/__init__.py tests/__init__.py tests/test_agents/__init__.py \
      tests/test_services/__init__.py tests/test_orchestrator/__init__.py \
      tests/test_routes/__init__.py
```

- [ ] **Install deps and verify**

```bash
pip install -r requirements.txt
python -c "import fastapi, anthropic, sqlalchemy; print('OK')"
```

Expected: `OK`

- [ ] **Commit**

```bash
git init && git add requirements.txt pyproject.toml .env.example .gitignore data/candidate_profile.yaml backend/__init__.py backend/agents/__init__.py backend/services/__init__.py backend/routes/__init__.py tests/__init__.py tests/test_agents/__init__.py tests/test_services/__init__.py tests/test_orchestrator/__init__.py tests/test_routes/__init__.py
git commit -m "chore: project skeleton and tooling"
```

---

### Task 2: Settings & Config

**Files:** Create `backend/config.py`, `tests/test_config.py`

- [ ] **Write failing test** — `tests/test_config.py`

```python
from backend.config import Settings

def test_settings_defaults():
    s = Settings(anthropic_api_key="sk-test", github_username="testuser")
    assert s.api_prefix == "/api"
    assert "aiosqlite" in s.database_url
    assert s.cv_path == "data/cv.pdf"

def test_settings_requires_api_key():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        Settings(github_username="testuser")  # type: ignore[call-arg]
```

- [ ] **Run — expect FAIL** `pytest tests/test_config.py -v`

- [ ] **Write `backend/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str
    github_username: str
    database_url: str = "sqlite+aiosqlite:///./data/jobfit.db"
    api_prefix: str = "/api"
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"

settings = Settings()
```

- [ ] **Run — expect PASS** `pytest tests/test_config.py -v`

- [ ] **Commit** `git commit -m "feat: settings singleton via pydantic-settings"`

---

### Task 3: Database Layer

**Files:** Create `backend/database.py`, `backend/models.py`, `tests/test_database.py`

- [ ] **Write failing test** — `tests/test_database.py`

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.database import Base
from backend.models import Profile, Analysis, JobResult

@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()

async def test_tables_created(engine):
    from sqlalchemy import inspect, text
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result}
    assert "profiles" in tables
    assert "analyses" in tables
    assert "job_results" in tables

async def test_profile_insert(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        p = Profile(yaml_data="name: test", cv_text="", github_data="{}", merged_profile="test")
        session.add(p)
        await session.commit()
        await session.refresh(p)
        assert p.id is not None
        assert p.last_refreshed_at is not None
```

- [ ] **Run — expect FAIL** `pytest tests/test_database.py -v`

- [ ] **Write `backend/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from backend.config import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Write `backend/models.py`**

```python
from __future__ import annotations
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    yaml_data: Mapped[str] = mapped_column(Text)
    cv_text: Mapped[str] = mapped_column(Text, default="")
    github_data: Mapped[str] = mapped_column(Text, default="{}")
    merged_profile: Mapped[str] = mapped_column(Text, default="")
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    jd_text: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[str] = mapped_column(String, ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
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

- [ ] **Run — expect PASS** `pytest tests/test_database.py -v`

- [ ] **Commit** `git commit -m "feat: database layer — engine, session, ORM models"`

---

### Task 4: Pydantic Schemas

**Files:** Create `backend/schemas.py`, `tests/test_schemas.py`

- [ ] **Write failing test** — `tests/test_schemas.py`

```python
from backend.schemas import (
    JobParserOutput, MatchScorerOutput, GapAnalystOutput, GapItem,
    ResourcePlannerOutput, ResourceItem, CoverLetterOutput,
    ResumeTailorerOutput, BulletItem, PriorOutputs, AnalyseRequest,
)
import pytest

def test_prior_outputs_all_optional():
    p = PriorOutputs()
    assert p.job_parser is None
    assert p.resume_tailorer is None

def test_match_scorer_score_range():
    with pytest.raises(Exception):
        MatchScorerOutput(score=150, matched_skills=[], missing_skills=[], partial_matches=[])

def test_analyse_request_min_length():
    with pytest.raises(Exception):
        AnalyseRequest(jd="short")
```

- [ ] **Run — expect FAIL** `pytest tests/test_schemas.py -v`

- [ ] **Write `backend/schemas.py`**

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

class GapItem(BaseModel):
    skill: str
    impact: str
    rationale: str

class ResourceItem(BaseModel):
    skill: str
    courses: list[str]
    books: list[str]
    projects: list[str]
    estimated_hours: int

class BulletItem(BaseModel):
    original: str
    rewritten: str
    rationale: str

class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str

class MatchScorerOutput(BaseModel):
    score: int = Field(..., ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    partial_matches: list[str]

class GapAnalystOutput(BaseModel):
    critical_gaps: list[GapItem]
    nice_to_have_gaps: list[GapItem]

class ResourcePlannerOutput(BaseModel):
    gaps: list[ResourceItem]

class CoverLetterOutput(BaseModel):
    subject: str
    body: str
    tone_notes: str

class ResumeTailorerOutput(BaseModel):
    tailored_bullets: list[BulletItem]

class PriorOutputs(BaseModel):
    job_parser: JobParserOutput | None = None
    match_scorer: MatchScorerOutput | None = None
    gap_analyst: GapAnalystOutput | None = None
    resource_planner: ResourcePlannerOutput | None = None
    cover_letter: CoverLetterOutput | None = None
    resume_tailorer: ResumeTailorerOutput | None = None

# Request / Response schemas
class AnalyseRequest(BaseModel):
    jd: str = Field(..., min_length=50, description="Full job description text")

class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    yaml_data: str
    cv_text: str
    github_data: str
    merged_profile: str
    last_refreshed_at: datetime

class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool

class AnalysisDetail(BaseModel):
    id: str
    jd_text: str
    profile_id: str
    created_at: datetime
    partial: bool
    results: dict[str, dict]  # type: ignore[type-arg]
```

- [ ] **Run — expect PASS** `pytest tests/test_schemas.py -v`

- [ ] **Commit** `git commit -m "feat: pydantic v2 schemas including PriorOutputs"`

---

## PHASE 2 — SERVICES

### Task 5: GitHub Client

**Files:** Create `backend/services/github_client.py`, `tests/test_services/test_github_client.py`

- [ ] **Write failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

async def test_fetch_readme_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "IyBEb2NDaGF0", "encoding": "base64"}  # base64("# DocChat")
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        from backend.services.github_client import fetch_readme
        result = await fetch_readme("divyanshu144/docchat")

    assert "DocChat" in result

async def test_fetch_readme_404_returns_empty():
    from httpx import HTTPStatusError, Request, Response
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        from backend.services.github_client import fetch_readme
        result = await fetch_readme("divyanshu144/nonexistent")

    assert result == ""
```

- [ ] **Run — expect FAIL** `pytest tests/test_services/test_github_client.py -v`

- [ ] **Write `backend/services/github_client.py`**

```python
import base64
import httpx

GITHUB_API = "https://api.github.com"

async def fetch_readme(repo: str) -> str:
    """Fetch decoded README text for a public repo. Returns '' on 404 or error."""
    url = f"{GITHUB_API}/repos/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return data.get("content", "")
        except httpx.HTTPStatusError:
            return ""
        except Exception:
            return ""

async def fetch_all_readmes(repos: list[str]) -> dict[str, str]:
    """Fetch READMEs for multiple repos concurrently."""
    import asyncio
    results = await asyncio.gather(*[fetch_readme(r) for r in repos])
    return dict(zip(repos, results))
```

- [ ] **Run — expect PASS** `pytest tests/test_services/test_github_client.py -v`

- [ ] **Commit** `git commit -m "feat: async github client for readme fetching"`

---

### Task 6: CV Parser

**Files:** Create `backend/services/cv_parser.py`, `tests/test_services/test_cv_parser.py`

- [ ] **Write failing test**

```python
import io
import pytest
from unittest.mock import patch, MagicMock

async def test_extract_text_from_bytes():
    # Mock pypdf to return known text
    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock(extract_text=MagicMock(return_value="Software Engineer\nPython FastAPI"))]

    with patch("backend.services.cv_parser.PdfReader", return_value=mock_reader):
        from backend.services.cv_parser import extract_text_from_pdf_bytes
        result = await extract_text_from_pdf_bytes(b"fake-pdf-bytes")

    assert "Python" in result
    assert "FastAPI" in result

async def test_extract_text_missing_file_returns_empty():
    from backend.services.cv_parser import extract_text_from_file
    result = await extract_text_from_file("nonexistent/path.pdf")
    assert result == ""
```

- [ ] **Run — expect FAIL** `pytest tests/test_services/test_cv_parser.py -v`

- [ ] **Write `backend/services/cv_parser.py`**

```python
import asyncio
import io
from pathlib import Path
from pypdf import PdfReader

def _extract_sync(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

async def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_sync, pdf_bytes)

async def extract_text_from_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return await extract_text_from_pdf_bytes(p.read_bytes())
```

- [ ] **Run — expect PASS** `pytest tests/test_services/test_cv_parser.py -v`

- [ ] **Commit** `git commit -m "feat: pypdf cv parser with run_in_executor"`

---

### Task 7: Profile Builder

**Files:** Create `backend/services/profile_builder.py`, `tests/test_services/test_profile_builder.py`

- [ ] **Write failing test**

```python
import pytest, json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.database import Base

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()

async def test_build_profile_merges_sources(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Test User\ncore_skills:\n  languages: [Python]\n")
    cv_path = tmp_path / "cv.pdf"  # doesn't exist — should return empty cv_text

    with patch("backend.services.profile_builder.fetch_all_readmes", new_callable=AsyncMock) as mock_gh:
        mock_gh.return_value = {"divyanshu144/docchat": "# DocChat README"}
        from backend.services.profile_builder import build_profile
        profile = await build_profile(session, str(yaml_path), str(cv_path))

    assert profile.id is not None
    assert "Test User" in profile.yaml_data
    assert profile.cv_text == ""
    github = json.loads(profile.github_data)
    assert "divyanshu144/docchat" in github
    assert "DocChat" in profile.merged_profile

async def test_get_or_build_returns_cached(session, tmp_path):
    yaml_path = tmp_path / "profile.yaml"
    yaml_path.write_text("identity:\n  name: Cached\nfeatured_projects: []\n")

    with patch("backend.services.profile_builder.fetch_all_readmes", new_callable=AsyncMock) as mock_gh:
        mock_gh.return_value = {}
        from backend.services.profile_builder import build_profile, get_or_build_profile
        p1 = await build_profile(session, str(yaml_path), str(tmp_path / "cv.pdf"))
        p2 = await get_or_build_profile(session)
    assert p1.id == p2.id
```

- [ ] **Run — expect FAIL** `pytest tests/test_services/test_profile_builder.py -v`

- [ ] **Write `backend/services/profile_builder.py`**

```python
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.config import settings
from backend.models import Profile
from backend.services.github_client import fetch_all_readmes
from backend.services.cv_parser import extract_text_from_file

def _assemble_merged(yaml_data: str, cv_text: str, github_data: dict[str, str]) -> str:
    parts = ["## Candidate Profile (YAML)\n" + yaml_data]
    if cv_text.strip():
        parts.append("## CV Text\n" + cv_text[:8000])
    for repo, readme in github_data.items():
        if readme.strip():
            parts.append(f"## GitHub: {repo}\n" + readme[:3000])
    return "\n\n---\n\n".join(parts)

async def build_profile(
    db: AsyncSession,
    yaml_path: str | None = None,
    cv_path: str | None = None,
) -> Profile:
    yaml_path = yaml_path or settings.profile_yaml_path
    cv_path = cv_path or settings.cv_path

    yaml_text = Path(yaml_path).read_text()
    profile_data = yaml.safe_load(yaml_text)

    repos: list[str] = [
        p["repo"] for p in profile_data.get("featured_projects", [])
        if isinstance(p, dict) and "repo" in p
    ]
    cv_text = await extract_text_from_file(cv_path)
    github_readmes = await fetch_all_readmes(repos) if repos else {}

    merged = _assemble_merged(yaml_text, cv_text, github_readmes)

    profile = Profile(
        yaml_data=yaml_text,
        cv_text=cv_text,
        github_data=json.dumps(github_readmes),
        merged_profile=merged,
        last_refreshed_at=datetime.utcnow(),
    )
    db.add(profile)
    await db.flush()
    return profile

async def get_or_build_profile(db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).order_by(Profile.last_refreshed_at.desc()).limit(1))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = await build_profile(db)
    return profile
```

- [ ] **Run — expect PASS** `pytest tests/test_services/test_profile_builder.py -v`

- [ ] **Commit** `git commit -m "feat: profile builder — merges yaml, cv, github readmes"`

---

## PHASE 3 — AGENTS

### Task 8: Base Agent & Prompt Templates

**Files:** Create `backend/agents/base.py`, `backend/prompts/*.md`

- [ ] **Write `backend/agents/base.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
import anthropic
from backend.config import settings
from backend.schemas import PriorOutputs

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

class BaseAgent:
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
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
```

- [ ] **Create `backend/prompts/job_parser.md`**

```markdown
# Job Parser

You are a technical recruitment analyst specialising in software engineering and data science roles.

## Candidate Profile
{profile}

## Task
Analyse the job description below. Extract structured role requirements.

## Job Description
{jd}

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"required_skills": ["list"], "nice_to_have": ["list"], "years_experience": null, "role_type": "string", "seniority": "Junior|Mid|Senior|Lead|Staff|Principal"}
```

- [ ] **Create `backend/prompts/match_scorer.md`**

```markdown
# Match Scorer

You are a technical recruiter comparing a candidate against job requirements.

## Candidate Profile
{profile}

## Parsed Job Requirements
{prior.job_parser}

## Job Description
{jd}

## Task
Score 0-100 how well the candidate matches. Be honest — under-scoring wastes their time, over-scoring leads to rejection.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"score": 0, "matched_skills": ["list"], "missing_skills": ["list"], "partial_matches": ["list"]}
```

- [ ] **Create `backend/prompts/gap_analyst.md`**

```markdown
# Gap Analyst

You are a career advisor identifying skill gaps.

## Candidate Profile
{profile}

## Match Analysis
{prior.match_scorer}

## Parsed Requirements
{prior.job_parser}

## Task
Classify gaps as critical (blocks application) or nice-to-have (optional).

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"critical_gaps": [{"skill": "", "impact": "", "rationale": ""}], "nice_to_have_gaps": [{"skill": "", "impact": "", "rationale": ""}]}
```

- [ ] **Create `backend/prompts/resource_planner.md`**

```markdown
# Resource Planner

You are a learning path designer for engineers upskilling for job applications.

## Candidate Profile
{profile}

## Critical Gaps
{prior.gap_analyst}

## Task
For each critical gap suggest concrete, free-first learning resources and a realistic time estimate.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"gaps": [{"skill": "", "courses": ["name (platform)"], "books": ["Title by Author"], "projects": ["mini project description"], "estimated_hours": 0}]}
```

- [ ] **Create `backend/prompts/cover_letter.md`**

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

## Task
Write a tailored cover letter. Ground everything in the candidate's actual experience — never invent skills, projects, or achievements not in the profile.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"subject": "Cover Letter – [role] at [company or 'Your Company']", "body": "3-4 paragraph letter", "tone_notes": "brief note on tone choices"}
```

- [ ] **Create `backend/prompts/resume_tailorer.md`**

```markdown
# Resume Tailorer

You are a professional CV writer specialising in tech roles.

## Candidate Profile
{profile}

## Job Requirements
{prior.job_parser}

## Match Analysis
{prior.match_scorer}

## Gap Analysis
{prior.gap_analyst}

## Task
Rewrite experience bullets using job description language where honest. Do not invent achievements, metrics, or technologies not in the profile or original bullets.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"tailored_bullets": [{"original": "", "rewritten": "", "rationale": ""}]}
```

- [ ] **Commit** `git commit -m "feat: base agent class and 6 prompt templates"`

---

### Task 9: Job Parser Agent

**Files:** Create `backend/agents/job_parser.py`, `tests/test_agents/test_job_parser.py`

- [ ] **Write failing tests** — `tests/test_agents/test_job_parser.py`

```python
import pytest, json
from unittest.mock import AsyncMock, patch
from backend.schemas import PriorOutputs, JobParserOutput

FIXTURE_JD = "We are looking for a Senior ML Engineer with 5+ years experience in Python, PyTorch, and deploying models to AWS. Nice to have: Kubernetes, Spark."

HAPPY_RESPONSE = json.dumps({
    "required_skills": ["Python", "PyTorch", "AWS"],
    "nice_to_have": ["Kubernetes", "Spark"],
    "years_experience": 5,
    "role_type": "ML Engineer",
    "seniority": "Senior"
})

MALFORMED_RESPONSES = [
    "Here is the analysis: " + HAPPY_RESPONSE,  # extra prose before JSON
    HAPPY_RESPONSE[:40],                          # truncated
    json.dumps({"required_skills": "not-a-list"}),  # type mismatch
]

@pytest.fixture
def mock_call():
    async def _call(self, system, user):
        return HAPPY_RESPONSE
    return _call

async def test_job_parser_happy_path(mock_call):
    from backend.agents.job_parser import JobParserAgent
    with patch.object(JobParserAgent, "_call", new=mock_call):
        agent = JobParserAgent()
        result = await agent.run("profile text", FIXTURE_JD, PriorOutputs())
    assert isinstance(result, JobParserOutput)
    assert "Python" in result.required_skills
    assert result.seniority == "Senior"

@pytest.mark.parametrize("bad_response", MALFORMED_RESPONSES)
async def test_job_parser_malformed_raises(bad_response):
    from backend.agents.job_parser import JobParserAgent, AgentError
    async def _bad_call(self, system, user):
        return bad_response
    with patch.object(JobParserAgent, "_call", new=_bad_call):
        agent = JobParserAgent()
        with pytest.raises(AgentError):
            await agent.run("profile text", FIXTURE_JD, PriorOutputs())
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_job_parser.py -v`

- [ ] **Write `backend/agents/job_parser.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.schemas import JobParserOutput, PriorOutputs

class AgentError(Exception):
    pass

def _parse_json(raw: str) -> dict:  # type: ignore[type-arg]
    """Extract and parse the first JSON object from a string."""
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise AgentError(f"No JSON object found in response: {raw[:100]}")
    return json.loads(raw[start:end])

class JobParserAgent(BaseAgent):
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

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_job_parser.py -v`

- [ ] **Commit** `git commit -m "feat: job_parser agent with malformed-response handling"`

---

### Task 10: Match Scorer Agent

**Files:** Create `backend/agents/match_scorer.py`, `tests/test_agents/test_match_scorer.py`

- [ ] **Write failing tests** — `tests/test_agents/test_match_scorer.py`

```python
import pytest, json
from unittest.mock import patch
from backend.schemas import PriorOutputs, MatchScorerOutput, JobParserOutput

PRIOR = PriorOutputs(job_parser=JobParserOutput(
    required_skills=["Python","PyTorch"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
))
HAPPY = json.dumps({"score": 78, "matched_skills": ["Python"], "missing_skills": ["PyTorch"], "partial_matches": []})
MALFORMED = [HAPPY[:20], json.dumps({"score": "high"}), "No JSON here"]

async def test_match_scorer_happy_path():
    from backend.agents.match_scorer import MatchScorerAgent
    async def _call(self, s, u): return HAPPY
    with patch.object(MatchScorerAgent, "_call", new=_call):
        result = await MatchScorerAgent().run("profile", "jd text " * 10, PRIOR)
    assert isinstance(result, MatchScorerOutput)
    assert 0 <= result.score <= 100

@pytest.mark.parametrize("bad", MALFORMED)
async def test_match_scorer_malformed(bad):
    from backend.agents.match_scorer import MatchScorerAgent, AgentError
    async def _call(self, s, u): return bad
    with patch.object(MatchScorerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await MatchScorerAgent().run("profile", "jd text " * 10, PRIOR)
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_match_scorer.py -v`

- [ ] **Write `backend/agents/match_scorer.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import MatchScorerOutput, PriorOutputs

class MatchScorerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> MatchScorerOutput:
        template = self._load_prompt("match_scorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return MatchScorerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"match_scorer: {e}") from e
```

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_match_scorer.py -v`

- [ ] **Commit** `git commit -m "feat: match_scorer agent"`

---

### Task 11: Gap Analyst Agent

**Files:** Create `backend/agents/gap_analyst.py`, `tests/test_agents/test_gap_analyst.py`

- [ ] **Write failing tests**

```python
import pytest, json
from unittest.mock import patch
from backend.schemas import PriorOutputs, GapAnalystOutput, MatchScorerOutput, JobParserOutput

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(required_skills=["Kubernetes"], nice_to_have=[], role_type="DevOps", seniority="Mid"),
    match_scorer=MatchScorerOutput(score=55, matched_skills=[], missing_skills=["Kubernetes"], partial_matches=[])
)
HAPPY = json.dumps({"critical_gaps": [{"skill": "Kubernetes", "impact": "core requirement", "rationale": "listed as required"}], "nice_to_have_gaps": []})
MALFORMED = [HAPPY[:15], json.dumps({"critical_gaps": "not-a-list"})]

async def test_gap_analyst_happy_path():
    from backend.agents.gap_analyst import GapAnalystAgent
    async def _call(self, s, u): return HAPPY
    with patch.object(GapAnalystAgent, "_call", new=_call):
        result = await GapAnalystAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, GapAnalystOutput)
    assert result.critical_gaps[0].skill == "Kubernetes"

@pytest.mark.parametrize("bad", MALFORMED)
async def test_gap_analyst_malformed(bad):
    from backend.agents.gap_analyst import GapAnalystAgent
    from backend.agents.job_parser import AgentError
    async def _call(self, s, u): return bad
    with patch.object(GapAnalystAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await GapAnalystAgent().run("profile", "jd " * 15, PRIOR)
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_gap_analyst.py -v`

- [ ] **Write `backend/agents/gap_analyst.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import GapAnalystOutput, PriorOutputs

class GapAnalystAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> GapAnalystOutput:
        template = self._load_prompt("gap_analyst")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return GapAnalystOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"gap_analyst: {e}") from e
```

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_gap_analyst.py -v`

- [ ] **Commit** `git commit -m "feat: gap_analyst agent"`

---

### Task 12: Resource Planner Agent

**Files:** Create `backend/agents/resource_planner.py`, `tests/test_agents/test_resource_planner.py`

- [ ] **Write failing tests**

```python
import pytest, json
from unittest.mock import patch
from backend.schemas import PriorOutputs, ResourcePlannerOutput, GapAnalystOutput, GapItem

PRIOR = PriorOutputs(
    gap_analyst=GapAnalystOutput(
        critical_gaps=[GapItem(skill="Kubernetes", impact="required", rationale="core")],
        nice_to_have_gaps=[]
    )
)
HAPPY = json.dumps({"gaps": [{"skill": "Kubernetes", "courses": ["K8s Basics (CNCF)"], "books": [], "projects": ["Deploy a FastAPI app to a local k3s cluster"], "estimated_hours": 20}]})
MALFORMED = [HAPPY[:10], json.dumps({"gaps": "not-a-list"})]

async def test_resource_planner_happy():
    from backend.agents.resource_planner import ResourcePlannerAgent
    async def _call(self, s, u): return HAPPY
    with patch.object(ResourcePlannerAgent, "_call", new=_call):
        result = await ResourcePlannerAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, ResourcePlannerOutput)
    assert result.gaps[0].skill == "Kubernetes"
    assert result.gaps[0].estimated_hours == 20

@pytest.mark.parametrize("bad", MALFORMED)
async def test_resource_planner_malformed(bad):
    from backend.agents.resource_planner import ResourcePlannerAgent
    from backend.agents.job_parser import AgentError
    async def _call(self, s, u): return bad
    with patch.object(ResourcePlannerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ResourcePlannerAgent().run("profile", "jd " * 15, PRIOR)
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_resource_planner.py -v`

- [ ] **Write `backend/agents/resource_planner.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import ResourcePlannerOutput, PriorOutputs

class ResourcePlannerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResourcePlannerOutput:
        template = self._load_prompt("resource_planner")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return ResourcePlannerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resource_planner: {e}") from e
```

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_resource_planner.py -v`

- [ ] **Commit** `git commit -m "feat: resource_planner agent"`

---

### Task 13: Cover Letter Agent

**Files:** Create `backend/agents/cover_letter.py`, `tests/test_agents/test_cover_letter.py`

- [ ] **Write failing tests**

```python
import pytest, json
from unittest.mock import patch
from backend.schemas import PriorOutputs, CoverLetterOutput, MatchScorerOutput, GapAnalystOutput, JobParserOutput

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"),
    match_scorer=MatchScorerOutput(score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]),
    gap_analyst=GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
)
HAPPY = json.dumps({"subject": "Cover Letter – ML Engineer", "body": "Dear Hiring Manager...", "tone_notes": "confident"})
MALFORMED = [HAPPY[:10], json.dumps({"subject": 123})]

async def test_cover_letter_happy():
    from backend.agents.cover_letter import CoverLetterAgent
    async def _call(self, s, u): return HAPPY
    with patch.object(CoverLetterAgent, "_call", new=_call):
        result = await CoverLetterAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, CoverLetterOutput)
    assert "ML Engineer" in result.subject

@pytest.mark.parametrize("bad", MALFORMED)
async def test_cover_letter_malformed(bad):
    from backend.agents.cover_letter import CoverLetterAgent
    from backend.agents.job_parser import AgentError
    async def _call(self, s, u): return bad
    with patch.object(CoverLetterAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await CoverLetterAgent().run("profile", "jd " * 15, PRIOR)
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_cover_letter.py -v`

- [ ] **Write `backend/agents/cover_letter.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import CoverLetterOutput, PriorOutputs

class CoverLetterAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> CoverLetterOutput:
        template = self._load_prompt("cover_letter")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return CoverLetterOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cover_letter: {e}") from e
```

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_cover_letter.py -v`

- [ ] **Commit** `git commit -m "feat: cover_letter agent"`

---

### Task 14: Resume Tailorer Agent

**Files:** Create `backend/agents/resume_tailorer.py`, `tests/test_agents/test_resume_tailorer.py`

- [ ] **Write failing tests**

```python
import pytest, json
from unittest.mock import patch
from backend.schemas import PriorOutputs, ResumeTailorerOutput, MatchScorerOutput, GapAnalystOutput, JobParserOutput

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Mid"),
    match_scorer=MatchScorerOutput(score=72, matched_skills=["Python"], missing_skills=[], partial_matches=[]),
    gap_analyst=GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
)
HAPPY = json.dumps({"tailored_bullets": [{"original": "Built ML pipeline", "rewritten": "Engineered end-to-end ML pipeline with Python", "rationale": "adds JD keyword"}]})
MALFORMED = [HAPPY[:10], json.dumps({"tailored_bullets": "not-a-list"})]

async def test_resume_tailorer_happy():
    from backend.agents.resume_tailorer import ResumeTailorerAgent
    async def _call(self, s, u): return HAPPY
    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        result = await ResumeTailorerAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, ResumeTailorerOutput)
    assert result.tailored_bullets[0].original == "Built ML pipeline"

@pytest.mark.parametrize("bad", MALFORMED)
async def test_resume_tailorer_malformed(bad):
    from backend.agents.resume_tailorer import ResumeTailorerAgent
    from backend.agents.job_parser import AgentError
    async def _call(self, s, u): return bad
    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ResumeTailorerAgent().run("profile", "jd " * 15, PRIOR)
```

- [ ] **Run — expect FAIL** `pytest tests/test_agents/test_resume_tailorer.py -v`

- [ ] **Write `backend/agents/resume_tailorer.py`**

```python
import json
from pydantic import ValidationError
from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import ResumeTailorerOutput, PriorOutputs

class ResumeTailorerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResumeTailorerOutput:
        template = self._load_prompt("resume_tailorer")
        system = self._inject(template, profile, jd, prior)
        raw = await self._call(system, jd)
        try:
            return ResumeTailorerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resume_tailorer: {e}") from e
```

- [ ] **Run — expect PASS** `pytest tests/test_agents/test_resume_tailorer.py -v`

- [ ] **Commit** `git commit -m "feat: resume_tailorer agent"`

---

### Task 15: Orchestrator + SSE

**Files:** Create `backend/services/orchestrator.py`, `tests/test_orchestrator/test_sse_sequence.py`

- [ ] **Write failing E2E test** — `tests/test_orchestrator/test_sse_sequence.py`

```python
import pytest, json
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.database import Base
from backend.schemas import (
    JobParserOutput, MatchScorerOutput, GapAnalystOutput,
    ResourcePlannerOutput, CoverLetterOutput, ResumeTailorerOutput
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

@pytest.fixture
def stub_agents():
    jp = JobParserOutput(required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior")
    ms = MatchScorerOutput(score=82, matched_skills=["Python"], missing_skills=[], partial_matches=[])
    ga = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])
    rp = ResourcePlannerOutput(gaps=[])
    cl = CoverLetterOutput(subject="Cover Letter", body="Dear...", tone_notes="confident")
    rt = ResumeTailorerOutput(tailored_bullets=[])
    return jp, ms, ga, rp, cl, rt

async def test_full_sse_event_sequence(session, stub_agents):
    jp, ms, ga, rp, cl, rt = stub_agents

    from backend.services.profile_builder import build_profile
    from pathlib import Path
    import tempfile, yaml as pyyaml

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        pyyaml.dump({"identity": {"name": "Test"}, "featured_projects": []}, f)
        yaml_path = f.name

    with (
        patch("backend.services.orchestrator.get_or_build_profile", new_callable=AsyncMock) as mock_profile,
        patch("backend.agents.job_parser.JobParserAgent.run", new_callable=AsyncMock, return_value=jp),
        patch("backend.agents.match_scorer.MatchScorerAgent.run", new_callable=AsyncMock, return_value=ms),
        patch("backend.agents.gap_analyst.GapAnalystAgent.run", new_callable=AsyncMock, return_value=ga),
        patch("backend.agents.resource_planner.ResourcePlannerAgent.run", new_callable=AsyncMock, return_value=rp),
        patch("backend.agents.cover_letter.CoverLetterAgent.run", new_callable=AsyncMock, return_value=cl),
        patch("backend.agents.resume_tailorer.ResumeTailorerAgent.run", new_callable=AsyncMock, return_value=rt),
    ):
        from backend.models import Profile
        from datetime import datetime
        mock_profile.return_value = Profile(
            id="test-profile-id", yaml_data="x", cv_text="", github_data="{}",
            merged_profile="profile text", last_refreshed_at=datetime.utcnow()
        )

        from backend.services.orchestrator import run_pipeline
        events = []
        async for event in run_pipeline(JD, session):
            events.append(event)

    names = [e.name for e in events]
    assert names[0] == "pipeline_start"
    assert names.count("agent_start") == 6
    assert names.count("agent_done") == 6
    assert names[-1] == "pipeline_done"

    # Verify Phase 1 sequential order
    starts = [e for e in events if e.name == "agent_start"]
    assert starts[0].data["agent"] == "job_parser"
    assert starts[1].data["agent"] == "match_scorer"
    assert starts[2].data["agent"] == "gap_analyst"
    assert starts[3].data["agent"] == "resource_planner"

    # Phase 2 parallel — both start before either done
    phase2_starts = starts[4:]
    assert {s.data["agent"] for s in phase2_starts} == {"cover_letter", "resume_tailorer"}

    # pipeline_done has analysis_id and score
    done = events[-1]
    assert "analysis_id" in done.data
    assert done.data["score"] == 82
    assert done.data["partial"] is False
```

- [ ] **Run — expect FAIL** `pytest tests/test_orchestrator/test_sse_sequence.py -v`

- [ ] **Write `backend/services/orchestrator.py`**

```python
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.job_parser import JobParserAgent, AgentError
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.models import Analysis, JobResult
from backend.schemas import PriorOutputs
from backend.services.profile_builder import get_or_build_profile

@dataclass
class SSEEvent:
    name: str
    data: dict  # type: ignore[type-arg]

async def run_pipeline(jd: str, db: AsyncSession) -> AsyncGenerator[SSEEvent, None]:
    profile = await get_or_build_profile(db)
    merged = profile.merged_profile

    yield SSEEvent("pipeline_start", {"total_agents": 6})

    results: dict[str, dict] = {}  # type: ignore[type-arg]
    partial = False
    prior = PriorOutputs()

    # Phase 1 — sequential
    phase1: list[tuple[str, object]] = [
        ("job_parser", JobParserAgent()),
        ("match_scorer", MatchScorerAgent()),
        ("gap_analyst", GapAnalystAgent()),
        ("resource_planner", ResourcePlannerAgent()),
    ]

    for agent_name, agent in phase1:
        yield SSEEvent("agent_start", {"agent": agent_name})
        try:
            output = await agent.run(merged, jd, prior)  # type: ignore[union-attr]
            prior = prior.model_copy(update={agent_name: output})
            results[agent_name] = output.model_dump()
            yield SSEEvent("agent_done", {"agent": agent_name, "output": output.model_dump()})
        except AgentError as e:
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(e)})

    # Phase 2 — parallel
    yield SSEEvent("agent_start", {"agent": "cover_letter"})
    yield SSEEvent("agent_start", {"agent": "resume_tailorer"})

    cl_result, rt_result = await asyncio.gather(
        CoverLetterAgent().run(merged, jd, prior),
        ResumeTailorerAgent().run(merged, jd, prior),
        return_exceptions=True,
    )

    for agent_name, result in [("cover_letter", cl_result), ("resume_tailorer", rt_result)]:
        if isinstance(result, Exception):
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(result)})
        else:
            results[agent_name] = result.model_dump()
            yield SSEEvent("agent_done", {"agent": agent_name, "output": result.model_dump()})

    # Persist to DB
    score = results.get("match_scorer", {}).get("score", 0)
    analysis = Analysis(jd_text=jd, profile_id=profile.id, partial=partial)
    db.add(analysis)
    await db.flush()

    for name, output in results.items():
        db.add(JobResult(
            analysis_id=analysis.id,
            agent_name=name,
            output_json=json.dumps(output),
        ))
    await db.commit()

    yield SSEEvent("pipeline_done", {"analysis_id": analysis.id, "score": score, "partial": partial})
```

- [ ] **Run — expect PASS** `pytest tests/test_orchestrator/test_sse_sequence.py -v`

- [ ] **Commit** `git commit -m "feat: two-phase orchestrator with SSE events"`

---

## PHASE 4 — ROUTES & MAIN

### Task 16: Profile Routes

**Files:** Create `backend/routes/profile.py`, `tests/test_routes/test_profile.py`

- [ ] **Write failing test** — `tests/test_routes/test_profile.py`

```python
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.database import Base, get_db

@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    from backend.main import app
    async def override_db():
        async with Session() as s:
            yield s
    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()

async def test_get_profile_builds_on_first_call(client):
    from unittest.mock import AsyncMock, patch
    with patch("backend.services.profile_builder.fetch_all_readmes", new_callable=AsyncMock, return_value={}), \
         patch("backend.services.cv_parser.extract_text_from_file", new_callable=AsyncMock, return_value=""):
        resp = await client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "merged_profile" in data

async def test_profile_refresh(client):
    from unittest.mock import AsyncMock, patch
    with patch("backend.services.profile_builder.fetch_all_readmes", new_callable=AsyncMock, return_value={}), \
         patch("backend.services.cv_parser.extract_text_from_file", new_callable=AsyncMock, return_value=""):
        resp = await client.post("/api/profile/refresh")
    assert resp.status_code == 200
    assert "last_refreshed_at" in resp.json()
```

- [ ] **Run — expect FAIL** `pytest tests/test_routes/test_profile.py -v`

- [ ] **Write `backend/routes/profile.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import ProfileResponse
from backend.services.profile_builder import get_or_build_profile, build_profile

router = APIRouter(tags=["profile"])

@router.get("/profile", response_model=ProfileResponse)
async def get_profile(db: AsyncSession = Depends(get_db)) -> ProfileResponse:
    profile = await get_or_build_profile(db)
    return ProfileResponse.model_validate(profile)

@router.post("/profile/refresh", response_model=ProfileResponse)
async def refresh_profile(db: AsyncSession = Depends(get_db)) -> ProfileResponse:
    profile = await build_profile(db)
    return ProfileResponse.model_validate(profile)
```

- [ ] **Run — expect PASS** `pytest tests/test_routes/test_profile.py -v`

- [ ] **Commit** `git commit -m "feat: profile routes GET and POST /refresh"`

---

### Task 17: Analyse Route (SSE)

**Files:** Create `backend/routes/analyse.py`, `tests/test_routes/test_analyse.py`

- [ ] **Write failing test** — `tests/test_routes/test_analyse.py`

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.database import Base, get_db
from backend.services.orchestrator import SSEEvent

async def make_events():
    yield SSEEvent("pipeline_start", {"total_agents": 6})
    yield SSEEvent("agent_start", {"agent": "job_parser"})
    yield SSEEvent("pipeline_done", {"analysis_id": "test-id", "score": 75, "partial": False})

@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    from backend.main import app
    async def override_db():
        async with Session() as s: yield s
    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()

async def test_analyse_streams_sse(client):
    jd = "Senior ML Engineer role requiring Python and PyTorch. " * 5

    with patch("backend.routes.analyse.run_pipeline", return_value=make_events()):
        resp = await client.post("/api/analyse", json={"jd": jd})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "pipeline_start" in resp.text
    assert "pipeline_done" in resp.text

async def test_analyse_rejects_short_jd(client):
    resp = await client.post("/api/analyse", json={"jd": "too short"})
    assert resp.status_code == 422
```

- [ ] **Run — expect FAIL** `pytest tests/test_routes/test_analyse.py -v`

- [ ] **Write `backend/routes/analyse.py`**

```python
from __future__ import annotations
import json
from typing import AsyncGenerator
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.schemas import AnalyseRequest
from backend.services.orchestrator import run_pipeline

router = APIRouter(tags=["analyse"])

async def _event_stream(jd: str, db: AsyncSession) -> AsyncGenerator[str, None]:
    async for event in run_pipeline(jd, db):
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
```

- [ ] **Run — expect PASS** `pytest tests/test_routes/test_analyse.py -v`

- [ ] **Commit** `git commit -m "feat: SSE streaming analyse route"`

---

### Task 18: History Routes

**Files:** Create `backend/routes/history.py`, `tests/test_routes/test_history.py`

- [ ] **Write failing test** — `tests/test_routes/test_history.py`

```python
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.database import Base, get_db
from backend.models import Profile, Analysis, JobResult
import json
from datetime import datetime

@pytest.fixture
async def client_with_data():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        p = Profile(yaml_data="x", cv_text="", github_data="{}", merged_profile="x", last_refreshed_at=datetime.utcnow())
        s.add(p)
        await s.flush()
        a = Analysis(jd_text="Senior ML Engineer " * 5, profile_id=p.id, partial=False)
        s.add(a)
        await s.flush()
        s.add(JobResult(analysis_id=a.id, agent_name="match_scorer", output_json=json.dumps({"score": 80})))
        await s.commit()
        analysis_id = a.id

    from backend.main import app
    async def override_db():
        async with Session() as s: yield s
    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, analysis_id
    app.dependency_overrides.clear()
    await engine.dispose()

async def test_list_history(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1

async def test_get_analysis_detail(client_with_data):
    client, analysis_id = client_with_data
    resp = await client.get(f"/api/analysis/{analysis_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == analysis_id
    assert "match_scorer" in data["results"]

async def test_history_pagination(client_with_data):
    client, _ = client_with_data
    resp = await client.get("/api/history?limit=0&offset=0")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Run — expect FAIL** `pytest tests/test_routes/test_history.py -v`

- [ ] **Write `backend/routes/history.py`**

```python
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import Analysis, JobResult
from backend.schemas import AnalysisSummary, AnalysisDetail

router = APIRouter(tags=["history"])

@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    result = await db.execute(
        select(Analysis).order_by(Analysis.created_at.desc()).limit(limit).offset(offset)
    )
    return [AnalysisSummary.model_validate(a) for a in result.scalars()]

@router.get("/analysis/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)) -> AnalysisDetail:
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_id).options(selectinload(Analysis.results))
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    results_map = {
        r.agent_name: json.loads(r.output_json) if r.output_json else {}
        for r in analysis.results
    }
    return AnalysisDetail(
        id=analysis.id,
        jd_text=analysis.jd_text,
        profile_id=analysis.profile_id,
        created_at=analysis.created_at,
        partial=analysis.partial,
        results=results_map,
    )
```

- [ ] **Run — expect PASS** `pytest tests/test_routes/test_history.py -v`

- [ ] **Commit** `git commit -m "feat: history routes GET /history and GET /analysis/{id}"`

---

### Task 19: FastAPI Main

**Files:** Create `backend/main.py`, `tests/conftest.py`

- [ ] **Write `tests/conftest.py`** (shared fixture, used by all route tests)

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from backend.database import Base, get_db

@pytest.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as session:
        yield session

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
```

- [ ] **Write `backend/main.py`**

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.database import init_db
from backend.routes.profile import router as profile_router
from backend.routes.analyse import router as analyse_router
from backend.routes.history import router as history_router

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
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

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Run all backend tests** `pytest tests/ -v --cov=backend`

  Expected: all pass, coverage ≥ 70%

- [ ] **Commit** `git commit -m "feat: fastapi main with lifespan, CORS, routers"`

---

## PHASE 5 — FRONTEND

### Task 20: Frontend Scaffold

**Files:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`

- [ ] **Scaffold Vite + React + TS project**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install react-router-dom
npm install lucide-react
npx shadcn@latest init
```

When shadcn prompts: style=`default`, base color=`slate`, CSS variables=`yes`.

- [ ] **Update `frontend/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

- [ ] **Update `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Update `frontend/vite.config.ts`** to proxy `/api` → backend

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
```

- [ ] **Verify dev server starts** `cd frontend && npm run dev`

  Expected: Vite server at `http://localhost:5173`

- [ ] **Commit** `git commit -m "feat: frontend scaffold — vite react ts tailwind shadcn"`

---

### Task 21: TypeScript Types

**Files:** Create `frontend/src/types/index.ts`

- [ ] **Write `frontend/src/types/index.ts`**

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
export interface ProfileResponse { id: string; yaml_data: string; cv_text: string; github_data: string; merged_profile: string; last_refreshed_at: string; }
export interface AnalysisSummary { id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean; }
export interface AnalysisDetail {
  id: string; jd_text: string; profile_id: string; created_at: string; partial: boolean;
  results: {
    job_parser?: JobParserOutput; match_scorer?: MatchScorerOutput;
    gap_analyst?: GapAnalystOutput; resource_planner?: ResourcePlannerOutput;
    cover_letter?: CoverLetterOutput; resume_tailorer?: ResumeTailorerOutput;
  };
}
export type AgentName = "job_parser"|"match_scorer"|"gap_analyst"|"resource_planner"|"cover_letter"|"resume_tailorer";
export const AGENT_ORDER: AgentName[] = ["job_parser","match_scorer","gap_analyst","resource_planner","cover_letter","resume_tailorer"];
export type AgentStatus = "pending"|"running"|"done"|"error";
export interface PipelineDoneData { analysis_id: string; score: number; partial: boolean; }
export interface SSECallbacks {
  onPipelineStart?: (data: { total_agents: number }) => void;
  onAgentStart?: (data: { agent: AgentName }) => void;
  onAgentDone?: (data: { agent: AgentName; output: unknown }) => void;
  onPipelineError?: (data: { agent: AgentName; error: string }) => void;
  onPipelineDone?: (data: PipelineDoneData) => void;
}
```

- [ ] **Commit** `git commit -m "feat: typescript types mirroring backend schemas"`

---

### Task 22: API Client

**Files:** Create `frontend/src/api/client.ts`

> `/api/analyse` is a POST endpoint. `EventSource` only supports GET — SSE consumed via `fetch` + `ReadableStream`.

- [ ] **Write `frontend/src/api/client.ts`**

```typescript
import type { ProfileResponse, AnalysisSummary, AnalysisDetail, AgentName, SSECallbacks } from "../types";

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
  listHistory: (limit = 20, offset = 0) => get<AnalysisSummary[]>(`/history?limit=${limit}&offset=${offset}`),
  getAnalysis: (id: string) => get<AnalysisDetail>(`/analysis/${id}`),
};

export function streamAnalysis(jd: string, callbacks: SSECallbacks): () => void {
  const controller = new AbortController();
  (async () => {
    const resp = await fetch(`${BASE}/analyse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd }),
      signal: controller.signal,
    });
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
```

- [ ] **Commit** `git commit -m "feat: typed api client with fetch+SSE streaming"`

---

### Task 23: UI Components

**Files:** Create all 5 components in `frontend/src/components/`

- [ ] **Write `frontend/src/components/AgentProgress.tsx`**

```tsx
import { AGENT_ORDER, AgentName, AgentStatus } from "../types";
const LABELS: Record<AgentName, string> = { job_parser:"Parse Job", match_scorer:"Score Match", gap_analyst:"Analyse Gaps", resource_planner:"Plan Resources", cover_letter:"Write Cover Letter", resume_tailorer:"Tailor Resume" };
function Icon({ s }: { s: AgentStatus }) {
  if (s==="pending") return <span className="w-4 h-4 rounded-full bg-slate-200 inline-block"/>;
  if (s==="running") return <span className="w-4 h-4 rounded-full bg-blue-400 animate-pulse inline-block"/>;
  if (s==="done") return <span className="text-green-500">✓</span>;
  return <span className="text-red-500">✗</span>;
}
export function AgentProgress({ agentStates }: { agentStates: Record<AgentName, AgentStatus> }) {
  return (
    <div className="space-y-2">
      {AGENT_ORDER.map((a) => (
        <div key={a} className="flex items-center gap-3 p-2 rounded-md bg-slate-50">
          <Icon s={agentStates[a]} /><span className="text-sm font-medium text-slate-700">{LABELS[a]}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Write `frontend/src/components/ScoreCard.tsx`**

```tsx
interface Props { score: number; matched: string[]; missing: string[]; partial: string[]; }
function Chips({ label, items, cls }: { label: string; items: string[]; cls: string }) {
  if (!items.length) return null;
  return <div><p className="text-xs font-semibold text-slate-500 uppercase mb-1">{label}</p><div className="flex flex-wrap gap-1">{items.map(s=><span key={s} className={`px-2 py-0.5 rounded-full text-xs ${cls}`}>{s}</span>)}</div></div>;
}
export function ScoreCard({ score, matched, missing, partial }: Props) {
  const c = score>=70?"text-green-600":score>=50?"text-amber-500":"text-red-500";
  return (
    <div className="p-6 rounded-xl border bg-white shadow-sm space-y-4">
      <div className="flex items-end gap-2"><span className={`text-6xl font-bold ${c}`}>{score}</span><span className="text-slate-400 text-xl mb-1">/100</span></div>
      <Chips label="Matched" items={matched} cls="bg-green-100 text-green-800"/>
      <Chips label="Partial" items={partial} cls="bg-amber-100 text-amber-800"/>
      <Chips label="Missing" items={missing} cls="bg-red-100 text-red-800"/>
    </div>
  );
}
```

- [ ] **Write `frontend/src/components/GapList.tsx`**

```tsx
import { GapItem } from "../types"; import { useState } from "react";
function Row({ item, critical }: { item: GapItem; critical: boolean }) {
  const [open, setOpen] = useState(false);
  const cls = critical ? "border-red-300 bg-red-50" : "border-amber-300 bg-amber-50";
  return (
    <div className={`border rounded-lg p-3 cursor-pointer ${cls}`} onClick={() => setOpen(!open)}>
      <div className="flex justify-between"><span className="font-medium">{item.skill}</span><span className="text-xs text-slate-400">{open?"▲":"▼"}</span></div>
      {open && <div className="mt-2 text-sm text-slate-600 space-y-1"><p><b>Impact:</b> {item.impact}</p><p><b>Why:</b> {item.rationale}</p></div>}
    </div>
  );
}
export function GapList({ critical, niceToHave }: { critical: GapItem[]; niceToHave: GapItem[] }) {
  return (
    <div className="space-y-4">
      {critical.length>0 && <div><h3 className="text-xs font-semibold text-red-600 uppercase mb-2">Critical</h3><div className="space-y-2">{critical.map(g=><Row key={g.skill} item={g} critical/>)}</div></div>}
      {niceToHave.length>0 && <div><h3 className="text-xs font-semibold text-amber-600 uppercase mb-2">Nice to Have</h3><div className="space-y-2">{niceToHave.map(g=><Row key={g.skill} item={g} critical={false}/>)}</div></div>}
      {!critical.length&&!niceToHave.length && <p className="text-slate-500 text-sm">No gaps identified.</p>}
    </div>
  );
}
```

- [ ] **Write `frontend/src/components/ResourcePanel.tsx`**

```tsx
import { ResourceItem } from "../types"; import { useState } from "react";
function Card({ item }: { item: ResourceItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg overflow-hidden">
      <button className="w-full flex justify-between p-4 bg-slate-50 text-left" onClick={()=>setOpen(!open)}>
        <span className="font-medium">{item.skill}</span><span className="text-xs text-slate-500">~{item.estimated_hours}h {open?"▲":"▼"}</span>
      </button>
      {open && <div className="p-4 space-y-2 text-sm">
        {item.courses.length>0&&<div><p className="font-semibold text-slate-600 mb-1">Courses</p><ul className="list-disc list-inside">{item.courses.map((c,i)=><li key={i}>{c}</li>)}</ul></div>}
        {item.books.length>0&&<div><p className="font-semibold text-slate-600 mb-1">Books</p><ul className="list-disc list-inside">{item.books.map((b,i)=><li key={i}>{b}</li>)}</ul></div>}
        {item.projects.length>0&&<div><p className="font-semibold text-slate-600 mb-1">Projects</p><ul className="list-disc list-inside">{item.projects.map((p,i)=><li key={i}>{p}</li>)}</ul></div>}
      </div>}
    </div>
  );
}
export function ResourcePanel({ gaps }: { gaps: ResourceItem[] }) {
  if (!gaps.length) return <p className="text-slate-500 text-sm">No resources needed.</p>;
  return <div className="space-y-4">{gaps.map(g=><Card key={g.skill} item={g}/>)}</div>;
}
```

- [ ] **Write `frontend/src/components/DocViewer.tsx`**

```tsx
import { useState } from "react";
export function DocViewer({ title, content, filename }: { title: string; content: string; filename: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(()=>setCopied(false),2000); };
  const download = () => { const b=new Blob([content],{type:"text/plain"}); const u=URL.createObjectURL(b); const a=document.createElement("a"); a.href=u; a.download=filename; a.click(); URL.revokeObjectURL(u); };
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="font-semibold text-slate-800">{title}</h3>
        <div className="flex gap-2">
          <button onClick={copy} className="px-3 py-1 text-xs rounded-md bg-slate-100 hover:bg-slate-200">{copied?"Copied!":"Copy"}</button>
          <button onClick={download} className="px-3 py-1 text-xs rounded-md bg-slate-100 hover:bg-slate-200">Download</button>
        </div>
      </div>
      <pre className="whitespace-pre-wrap text-sm bg-slate-50 rounded-lg p-4 border overflow-auto max-h-96">{content}</pre>
    </div>
  );
}
```

- [ ] **Commit** `git commit -m "feat: all 5 UI components"`

---

### Task 24: Pages + App Router

**Files:** Create `frontend/src/pages/ProfileSetup.tsx`, `AnalyseJob.tsx`, `Results.tsx`, `History.tsx`, `frontend/src/App.tsx`

- [ ] **Write `frontend/src/pages/ProfileSetup.tsx`**

```tsx
import { useState, useEffect } from "react";
import { api } from "../api/client";
import { ProfileResponse } from "../types";
export function ProfileSetup() {
  const [profile, setProfile] = useState<ProfileResponse|null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  useEffect(() => { setLoading(true); api.getProfile().then(setProfile).catch(e=>setError(String(e))).finally(()=>setLoading(false)); }, []);
  const refresh = async () => { setLoading(true); setError(null); try { setProfile(await api.refreshProfile()); } catch(e){setError(String(e));} finally{setLoading(false);} };
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-900">Candidate Profile</h1>
        <button onClick={refresh} disabled={loading} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">{loading?"Refreshing…":"Refresh"}</button>
      </div>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {profile && <>
        <div><h2 className="text-xs font-semibold text-slate-500 uppercase mb-2">YAML Profile</h2><pre className="text-xs bg-slate-50 p-3 rounded border overflow-auto max-h-64">{profile.yaml_data}</pre></div>
        {profile.cv_text && <div><h2 className="text-xs font-semibold text-slate-500 uppercase mb-2">CV Text</h2><p className="text-sm text-slate-600 whitespace-pre-wrap">{profile.cv_text.slice(0,500)}…</p></div>}
        <p className="text-xs text-slate-400">Last refreshed: {new Date(profile.last_refreshed_at).toLocaleString()}</p>
      </>}
    </div>
  );
}
```

- [ ] **Write `frontend/src/pages/AnalyseJob.tsx`**

```tsx
import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { streamAnalysis } from "../api/client";
import { AgentProgress } from "../components/AgentProgress";
import { AGENT_ORDER, AgentName, AgentStatus } from "../types";
const initStates = () => Object.fromEntries(AGENT_ORDER.map(a=>[a,"pending"])) as Record<AgentName,AgentStatus>;
export function AnalyseJob() {
  const [jd, setJd] = useState("");
  const [running, setRunning] = useState(false);
  const [states, setStates] = useState<Record<AgentName,AgentStatus>>(initStates());
  const [error, setError] = useState<string|null>(null);
  const cancelRef = useRef<(()=>void)|null>(null);
  const navigate = useNavigate();
  const submit = () => {
    if (jd.trim().length<50) { setError("JD must be at least 50 characters."); return; }
    setError(null); setRunning(true); setStates(initStates());
    cancelRef.current = streamAnalysis(jd, {
      onAgentStart: ({agent}) => setStates(p=>({...p,[agent]:"running"})),
      onAgentDone: ({agent}) => setStates(p=>({...p,[agent]:"done"})),
      onPipelineError: ({agent}) => setStates(p=>({...p,[agent]:"error"})),
      onPipelineDone: ({analysis_id}) => { setRunning(false); navigate(`/results/${analysis_id}`); },
    });
  };
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Analyse a Job</h1>
      <textarea className="w-full h-48 p-3 rounded-lg border border-slate-300 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Paste the full job description here…" value={jd} onChange={e=>setJd(e.target.value)} disabled={running}/>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button onClick={submit} disabled={running} className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50">{running?"Running…":"Analyse"}</button>
      {running && <AgentProgress agentStates={states}/>}
    </div>
  );
}
```

- [ ] **Write `frontend/src/pages/Results.tsx`**

```tsx
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { AnalysisDetail } from "../types";
import { ScoreCard } from "../components/ScoreCard";
import { GapList } from "../components/GapList";
import { ResourcePanel } from "../components/ResourcePanel";
import { DocViewer } from "../components/DocViewer";
type Tab = "score"|"gaps"|"resources"|"letter"|"resume";
const TABS: {id:Tab;label:string}[] = [{id:"score",label:"Score"},{id:"gaps",label:"Gaps"},{id:"resources",label:"Resources"},{id:"letter",label:"Cover Letter"},{id:"resume",label:"Resume"}];
export function Results() {
  const { id } = useParams<{id:string}>();
  const [data, setData] = useState<AnalysisDetail|null>(null);
  const [tab, setTab] = useState<Tab>("score");
  const [error, setError] = useState<string|null>(null);
  useEffect(() => { if (id) api.getAnalysis(id).then(setData).catch(e=>setError(String(e))); }, [id]);
  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!data) return <p className="p-6 text-slate-500">Loading…</p>;
  const r = data.results;
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Results</h1>
      {data.partial && <p className="text-amber-600 text-sm">⚠ Partial results — some agents failed.</p>}
      <div className="flex gap-2 border-b">{TABS.map(t=><button key={t.id} onClick={()=>setTab(t.id)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab===t.id?"border-blue-600 text-blue-600":"border-transparent text-slate-500 hover:text-slate-700"}`}>{t.label}</button>)}</div>
      <div className="pt-2">
        {tab==="score" && r.match_scorer && <ScoreCard score={r.match_scorer.score} matched={r.match_scorer.matched_skills} missing={r.match_scorer.missing_skills} partial={r.match_scorer.partial_matches}/>}
        {tab==="gaps" && r.gap_analyst && <GapList critical={r.gap_analyst.critical_gaps} niceToHave={r.gap_analyst.nice_to_have_gaps}/>}
        {tab==="resources" && r.resource_planner && <ResourcePanel gaps={r.resource_planner.gaps}/>}
        {tab==="letter" && r.cover_letter && <DocViewer title="Cover Letter" content={r.cover_letter.body} filename="cover_letter.txt"/>}
        {tab==="resume" && r.resume_tailorer && <div className="space-y-4">{r.resume_tailorer.tailored_bullets.map((b,i)=><div key={i} className="border rounded-lg p-4 space-y-2 text-sm"><p className="text-slate-400 line-through">{b.original}</p><p className="text-slate-900 font-medium">{b.rewritten}</p><p className="text-xs text-slate-400 italic">{b.rationale}</p></div>)}</div>}
      </div>
    </div>
  );
}
```

- [ ] **Write `frontend/src/pages/History.tsx`**

```tsx
import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { AnalysisSummary } from "../types";
export function History() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.listHistory().then(setItems).finally(()=>setLoading(false)); }, []);
  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">History</h1>
      {!items.length && <p className="text-slate-500 text-sm">No analyses yet.</p>}
      <div className="space-y-2">{items.map(item=>(
        <Link key={item.id} to={`/results/${item.id}`} className="block p-4 rounded-lg border hover:bg-slate-50">
          <p className="text-sm text-slate-700">{item.jd_text.slice(0,120)}…</p>
          <p className="text-xs text-slate-400 mt-1">{new Date(item.created_at).toLocaleString()}</p>
          {item.partial && <span className="text-xs text-amber-600">partial</span>}
        </Link>
      ))}</div>
    </div>
  );
}
```

- [ ] **Write `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { History } from "./pages/History";
const link = ({ isActive }: { isActive: boolean }) => `px-3 py-2 text-sm font-medium rounded-md ${isActive?"bg-blue-100 text-blue-700":"text-slate-600 hover:text-slate-900"}`;
export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center gap-4">
          <span className="font-bold text-slate-900 mr-4">JobFit</span>
          <NavLink to="/" end className={link}>Profile</NavLink>
          <NavLink to="/analyse" className={link}>Analyse</NavLink>
          <NavLink to="/history" className={link}>History</NavLink>
        </nav>
        <main className="py-8">
          <Routes>
            <Route path="/" element={<ProfileSetup/>}/>
            <Route path="/analyse" element={<AnalyseJob/>}/>
            <Route path="/results/:id" element={<Results/>}/>
            <Route path="/history" element={<History/>}/>
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

- [ ] **Start dev server and verify app loads**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173` — nav with Profile / Analyse / History should render.

- [ ] **Commit** `git commit -m "feat: all pages and App router wired"`

---

## PHASE 6 — INFRASTRUCTURE & QUALITY

### Task 25: Makefile, Dockerfile, docker-compose

**Files:** Create `Makefile`, `Dockerfile`, `docker-compose.yml`

- [ ] **Write `Makefile`**

```makefile
.PHONY: run test fmt lint docker-up

run:
	uvicorn backend.main:app --reload --port 8000 & cd frontend && npm run dev

test:
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-fail-under=70

fmt:
	ruff format backend/ tests/

lint:
	ruff check backend/ tests/
	mypy backend/
	python scripts/check_schema_drift.py

docker-up:
	docker-compose up --build
```

- [ ] **Write `Dockerfile`**

```dockerfile
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN mkdir -p data
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Write `docker-compose.yml`**

```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
```

- [ ] **Commit** `git commit -m "feat: Makefile, Dockerfile, docker-compose"`

---

### Task 26: Pydantic→TS Drift Check

**Files:** Create `scripts/check_schema_drift.py`

- [ ] **Write `scripts/check_schema_drift.py`**

```python
#!/usr/bin/env python3
"""Exits 1 if field names in backend/schemas.py diverge from frontend/src/types/index.ts."""
import re, sys
from pathlib import Path

PY = Path("backend/schemas.py").read_text()
TS = Path("frontend/src/types/index.ts").read_text()

PAIRS = [("JobParserOutput","JobParserOutput"),("MatchScorerOutput","MatchScorerOutput"),
         ("GapAnalystOutput","GapAnalystOutput"),("ResourcePlannerOutput","ResourcePlannerOutput"),
         ("CoverLetterOutput","CoverLetterOutput"),("ResumeTailorerOutput","ResumeTailorerOutput"),
         ("GapItem","GapItem"),("ResourceItem","ResourceItem"),("BulletItem","BulletItem")]

def py_fields(name: str) -> set:
    m = re.search(rf"class {name}\(BaseModel\):(.*?)(?=\nclass |\Z)", PY, re.DOTALL)
    return set(re.findall(r"^\s{4}(\w+)\s*:", m.group(1), re.MULTILINE)) - {"model_config"} if m else set()

def ts_fields(name: str) -> set:
    m = re.search(rf"interface {name}\s*\{{(.*?)\}}", TS, re.DOTALL)
    return set(re.findall(r"^\s{2}(\w+)\??:", m.group(1), re.MULTILINE)) if m else set()

errors = []
for py_name, ts_name in PAIRS:
    pf, tf = py_fields(py_name), ts_fields(ts_name)
    if not pf: errors.append(f"Python class {py_name} not found"); continue
    if not tf: errors.append(f"TS interface {ts_name} not found"); continue
    if pf - tf: errors.append(f"{py_name}: Python-only fields: {pf-tf}")
    if tf - pf: errors.append(f"{ts_name}: TS-only fields: {tf-pf}")

if errors:
    print("❌ Schema drift:"); [print(f"  {e}") for e in errors]; sys.exit(1)
print(f"✓ Schema drift check passed ({len(PAIRS)} classes)")
```

- [ ] **Verify** `python scripts/check_schema_drift.py`

  Expected: `✓ Schema drift check passed (9 classes)`

- [ ] **Commit** `git commit -m "feat: pydantic-to-ts schema drift check"`

---

### Task 27: Final Integration

- [ ] **Run formatter** `make fmt`

  Expected: files reformatted, no errors

- [ ] **Run linter** `make lint`

  Fix ruff/mypy errors. Common issues:
  - Missing `from __future__ import annotations` at top of files with forward refs
  - `# type: ignore[union-attr]` where mypy strict mode rejects Optional chaining
  - All route functions need explicit return type annotations

- [ ] **Run tests** `make test`

  Expected: all 19+ tests pass, coverage ≥ 70%

  If below 70%, find lowest-coverage modules:
  ```bash
  pytest tests/ --cov=backend --cov-report=term-missing | grep -E "^backend" | sort -k4 -rn | tail -10
  ```

- [ ] **Smoke test backend**

  ```bash
  cp .env.example .env  # fill in ANTHROPIC_API_KEY and GITHUB_USERNAME
  uvicorn backend.main:app --reload --port 8000
  curl http://localhost:8000/health
  ```
  Expected: `{"status":"ok"}`

- [ ] **Manual frontend test**

  1. `cd frontend && npm run dev`
  2. Open `http://localhost:5173`
  3. Profile page: loads and shows YAML
  4. Analyse page: paste real JD (50+ chars), submit
  5. Verify Phase 1 agent slots fire sequentially, Phase 2 two spinners fire together
  6. On `pipeline_done` browser navigates to `/results/:id`
  7. All 5 tabs render data

- [ ] **Final commit** `git commit -m "chore: integration verified — lint, tests, manual smoke test"`

---

## Self-Review

**Spec coverage:** All 17 design requirements traced to tasks:
- Match score + ScoreCard → Tasks 10, 23
- Gap analysis + GapList → Tasks 11, 23
- Learning resources + ResourcePanel → Tasks 12, 23
- Cover letter + DocViewer → Tasks 13, 23
- Resume bullets + resume tab → Tasks 14, 23
- Phase 1 sequential, Phase 2 parallel `asyncio.gather(return_exceptions=True)` → Task 15
- SSE per-agent events, `pipeline_done` always fires with `partial` → Tasks 15, 17
- SSE client closes on terminal event → Task 22
- `AnalyseJob` navigates to `/results/:id` → Task 24
- `PriorOutputs` typed Pydantic model → Task 4
- `last_refreshed_at` on Profile → Task 3
- `/api/history` paginated → Task 18
- Pydantic→TS drift check in `make lint` → Task 26
- 2 tests/agent (12 total) + 1 SSE E2E + 3 service + 3 route = 19 minimum → Tasks 9-18
- `--cov-fail-under=70` → Task 1 (`pyproject.toml`)
- `make fmt` with `ruff format` → Task 25
- Alembic deferred ✓ (not in plan)

**No placeholders detected.** All steps contain actual code.

**Type consistency check:** `PriorOutputs` defined in Task 4 with fields `job_parser`, `match_scorer`, `gap_analyst`, `resource_planner`, `cover_letter`, `resume_tailorer` — used consistently in orchestrator (Task 15) via `prior.model_copy(update={agent_name: output})` and in Phase 2 agents (Tasks 13, 14).
