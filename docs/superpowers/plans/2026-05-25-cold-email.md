# Cold Email Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Cold Email tab to the Results page that discovers contacts via Hunter.io, drafts a personalized cold email with an LLM, and sends it via Gmail (stubbed in V1).

**Architecture:** Four-endpoint REST API under `/api/contacts` backed by a new `contacts` table; `ColdEmailAgent(BaseAgent)` drafts emails from a template; frontend has three screens (contact picker, draft review, sent confirmation) driven by DB state loaded on tab mount.

**Tech Stack:** Python/FastAPI/SQLAlchemy async, httpx (Hunter.io), Anthropic SDK (ColdEmailAgent), React 18/TypeScript/Tailwind/shadcn-ui

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/models.py` | Modify | Add `Contact` ORM model |
| `scripts/migrate.py` | Modify | Step 17: create `contacts` table |
| `backend/config.py` | Modify | Add `hunter_api_key: str = ""` |
| `backend/schemas.py` | Modify | Add `company` to `JobParserOutput`; add `ColdEmailOutput`, `ContactRead`, `DiscoverRequest`, `DraftResponse`, `SendResponse` |
| `backend/prompts/job_parser.md` | Modify | Add `company` to output schema |
| `backend/services/contact_discovery.py` | Create | Hunter.io lookup, rank, bulk-insert contacts |
| `backend/agents/cold_email_agent.py` | Create | `ColdEmailAgent(BaseAgent)` |
| `backend/prompts/cold_email.md` | Create | Cold email prompt template |
| `backend/routes/contacts.py` | Create | 4 endpoints: list, discover, draft, send |
| `backend/main.py` | Modify | Register contacts router |
| `tests/test_services/test_contact_discovery.py` | Create | Discovery service unit tests |
| `tests/test_routes/test_contacts.py` | Create | Route integration tests |
| `frontend/src/types/index.ts` | Modify | Add `Contact`, `ColdEmailDraft` |
| `frontend/src/api/client.ts` | Modify | Add `getContacts`, `discoverContacts`, `draftEmail`, `sendEmail` |
| `frontend/src/pages/Results.tsx` | Modify | Add "Cold Email" tab + 3-screen flow |

---

### Task 1: Contact ORM model + migration

**Files:**
- Modify: `backend/models.py`
- Modify: `scripts/migrate.py`

- [ ] **Step 1: Add Contact model to `backend/models.py`**

Add this class after the `JobResult` class at the end of the file:

```python
class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String, ForeignKey("analyses.id"))
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    title: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    company: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    source: Mapped[str] = mapped_column(String, default="hunter")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="discovered")
    draft_subject: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

`Float`, `Text`, `DateTime` are already imported. No new imports needed.

- [ ] **Step 2: Add migration step 17 to `scripts/migrate.py`**

Add this block before `conn.commit()` at the end of `main()`:

```python
    # 17. Create contacts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id           TEXT PRIMARY KEY,
            analysis_id  TEXT NOT NULL REFERENCES analyses(id),
            email        TEXT NOT NULL,
            name         TEXT,
            title        TEXT,
            company      TEXT,
            source       TEXT NOT NULL DEFAULT 'hunter',
            confidence   REAL NOT NULL DEFAULT 0.0,
            status       TEXT NOT NULL DEFAULT 'discovered',
            draft_subject TEXT,
            draft_text   TEXT,
            sent_at      TIMESTAMP,
            created_at   TIMESTAMP NOT NULL
        )
    """)
    print("✓ contacts table ready")
```

- [ ] **Step 3: Verify model is registered with Base.metadata**

Run:
```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python -c "import backend.models; print([t for t in backend.models.Base.metadata.tables])"
```

Expected output includes `'contacts'`.

- [ ] **Step 4: Commit**

```bash
git add backend/models.py scripts/migrate.py
git commit -m "feat: add Contact ORM model and contacts migration step 17"
```

---

### Task 2: Config + schemas

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/schemas.py`
- Modify: `backend/prompts/job_parser.md`

- [ ] **Step 1: Add `hunter_api_key` to `backend/config.py`**

Add after `jwt_expire_minutes`:
```python
    hunter_api_key: str = ""
```

Full file after change:
```python
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    github_username: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/jobfit.db"
    api_prefix: str = "/api"
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"
    github_stale_days: int = 3
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    hunter_api_key: str = ""


settings = Settings()
```

- [ ] **Step 2: Add `company` field to `JobParserOutput` in `backend/schemas.py`**

Change:
```python
class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str
```

To:
```python
class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None = None
    role_type: str
    seniority: str
    company: str | None = None
```

The `None` default means existing stored JSON without `company` still deserializes without error.

- [ ] **Step 3: Add new schemas to `backend/schemas.py`**

Append to the end of `backend/schemas.py`:

```python
class ColdEmailOutput(BaseModel):
    subject: str
    body: str


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    analysis_id: str
    email: str
    name: str | None
    title: str | None
    company: str | None
    source: str
    confidence: float
    status: str
    draft_subject: str | None
    draft_text: str | None
    sent_at: datetime | None
    created_at: datetime


class DiscoverRequest(BaseModel):
    analysis_id: str
    domain: str | None = None


class DraftResponse(BaseModel):
    subject: str
    body: str


class SendResponse(BaseModel):
    sent: bool
```

`ConfigDict` is already imported at the top of `schemas.py`.

- [ ] **Step 4: Update job_parser prompt to extract company**

Edit `backend/prompts/job_parser.md`. Change the output schema line from:
```
{"required_skills": ["list"], "nice_to_have": ["list"], "years_experience": null, "role_type": "string", "seniority": "Junior|Mid|Senior|Lead|Staff|Principal"}
```

To:
```
{"required_skills": ["list"], "nice_to_have": ["list"], "years_experience": null, "role_type": "string", "seniority": "Junior|Mid|Senior|Lead|Staff|Principal", "company": "string or null"}
```

- [ ] **Step 5: Verify schemas import cleanly**

```bash
python -c "from backend.schemas import ColdEmailOutput, ContactRead, DiscoverRequest, DraftResponse, SendResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/schemas.py backend/prompts/job_parser.md
git commit -m "feat: add hunter_api_key config, cold email schemas, company field to job_parser output"
```

---

### Task 3: Hunter.io contact discovery service

**Files:**
- Create: `backend/services/contact_discovery.py`
- Create: `tests/test_services/test_contact_discovery.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_contact_discovery.py`:

```python
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.models  # noqa: F401
from backend.database import Base
from backend.models import Analysis, Contact, JobResult, Profile, User
from backend.services.contact_discovery import (
    ContactDiscoveryUnavailable,
    _title_rank,
    discover_contacts,
)


@pytest.fixture
async def mem_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def analysis_with_jp(mem_db):
    """Insert a Profile, Analysis, and job_parser JobResult with company='Stripe'."""
    profile = Profile(
        id="prof-1", yaml_data="", cv_text="", github_data="{}", merged_profile="test profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    mem_db.add(profile)
    analysis = Analysis(
        id="anal-1", jd_text="test jd", profile_id="prof-1",
        created_at=datetime.now(timezone.utc), partial=False,
    )
    mem_db.add(analysis)
    jp = JobResult(
        id="jr-1", analysis_id="anal-1", agent_name="job_parser",
        output_json=json.dumps({"company": "Stripe", "required_skills": [], "nice_to_have": [],
                                "role_type": "Engineering", "seniority": "Senior"}),
    )
    mem_db.add(jp)
    await mem_db.commit()
    return analysis


def test_title_rank_hiring_manager():
    assert _title_rank("Senior Hiring Manager") == 0


def test_title_rank_unknown():
    assert _title_rank("Data Analyst") == 4  # len(TITLE_PRIORITY)


def test_title_rank_none():
    assert _title_rank(None) == 4


@pytest.mark.asyncio
async def test_discover_contacts_happy_path(analysis_with_jp, mem_db):
    hunter_response = {
        "data": {
            "emails": [
                {"value": "alice@stripe.com", "first_name": "Alice", "last_name": "Chen",
                 "position": "Engineering Manager", "confidence": 94},
                {"value": "bob@stripe.com", "first_name": "Bob", "last_name": "Smith",
                 "position": "Recruiter", "confidence": 72},
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", mem_db)

    assert len(contacts) == 2
    assert contacts[0].email == "alice@stripe.com"  # Engineering Manager ranked higher
    assert contacts[0].confidence == pytest.approx(0.94)
    assert contacts[0].status == "discovered"
    assert contacts[0].source == "hunter"


@pytest.mark.asyncio
async def test_discover_contacts_filters_no_email(analysis_with_jp, mem_db):
    hunter_response = {
        "data": {
            "emails": [
                {"value": "alice@stripe.com", "confidence": 90, "position": "Recruiter"},
                {"value": "", "confidence": 80, "position": "Engineer"},  # no email — filtered
                {"confidence": 70, "position": "Manager"},  # missing value key — filtered
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", mem_db)

    assert len(contacts) == 1
    assert contacts[0].email == "alice@stripe.com"


@pytest.mark.asyncio
async def test_discover_contacts_raises_on_http_error(analysis_with_jp, mem_db):
    import httpx
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(ContactDiscoveryUnavailable):
            await discover_contacts("anal-1", mem_db)


@pytest.mark.asyncio
async def test_discover_contacts_raises_domain_required_when_no_company(mem_db):
    profile = Profile(
        id="prof-2", yaml_data="", cv_text="", github_data="{}", merged_profile="",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    mem_db.add(profile)
    analysis = Analysis(
        id="anal-2", jd_text="test jd", profile_id="prof-2",
        created_at=datetime.now(timezone.utc), partial=False,
    )
    mem_db.add(analysis)
    # job_parser has no company field
    jp = JobResult(
        id="jr-2", analysis_id="anal-2", agent_name="job_parser",
        output_json=json.dumps({"company": None, "required_skills": [], "nice_to_have": [],
                                "role_type": "Engineering", "seniority": "Senior"}),
    )
    mem_db.add(jp)
    await mem_db.commit()

    with pytest.raises(ValueError, match="domain_required"):
        await discover_contacts("anal-2", mem_db, domain=None)


@pytest.mark.asyncio
async def test_discover_contacts_uses_supplied_domain(analysis_with_jp, mem_db):
    hunter_response = {"data": {"emails": [
        {"value": "carol@customdomain.io", "confidence": 85, "position": "Founder"},
    ]}}
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", mem_db, domain="customdomain.io")

    # Verify Hunter.io was called with the supplied domain
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["domain"] == "customdomain.io"
    assert len(contacts) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python -m pytest tests/test_services/test_contact_discovery.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` for `contact_discovery`.

- [ ] **Step 3: Create `backend/services/contact_discovery.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Analysis, Contact, JobResult


class ContactDiscoveryUnavailable(Exception):
    pass


TITLE_PRIORITY = ["hiring manager", "engineering manager", "recruiter", "founder"]


def _title_rank(title: str | None) -> int:
    if not title:
        return len(TITLE_PRIORITY)
    t = title.lower()
    for i, keyword in enumerate(TITLE_PRIORITY):
        if keyword in t:
            return i
    return len(TITLE_PRIORITY)


async def discover_contacts(
    analysis_id: str,
    db: AsyncSession,
    domain: str | None = None,
) -> list[Contact]:
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None:
        raise ValueError(f"Analysis {analysis_id} not found")

    jp_row = (
        await db.execute(
            select(JobResult).where(
                JobResult.analysis_id == analysis_id,
                JobResult.agent_name == "job_parser",
            )
        )
    ).scalar_one_or_none()

    company: str | None = None
    if jp_row and jp_row.output_json:
        try:
            company = json.loads(jp_row.output_json).get("company")
        except (json.JSONDecodeError, AttributeError):
            pass

    if domain is None:
        if not company:
            raise ValueError("domain_required")
        domain = company.lower().replace(" ", "") + ".com"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "limit": 10, "api_key": settings.hunter_api_key},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ContactDiscoveryUnavailable(str(e)) from e
        except httpx.RequestError as e:
            raise ContactDiscoveryUnavailable(str(e)) from e

    emails = resp.json().get("data", {}).get("emails", [])
    emails = [e for e in emails if e.get("value")]
    emails.sort(key=lambda e: _title_rank(e.get("position")))

    contacts: list[Contact] = []
    for e in emails:
        first = e.get("first_name", "") or ""
        last = e.get("last_name", "") or ""
        full_name = f"{first} {last}".strip() or None
        contact = Contact(
            id=str(uuid4()),
            analysis_id=analysis_id,
            email=e["value"],
            name=full_name,
            title=e.get("position"),
            company=company,
            source="hunter",
            confidence=float(e.get("confidence", 0)) / 100.0,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        )
        db.add(contact)
        contacts.append(contact)

    await db.commit()
    return contacts
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_services/test_contact_discovery.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/contact_discovery.py tests/test_services/test_contact_discovery.py
git commit -m "feat: Hunter.io contact discovery service with tests"
```

---

### Task 4: ColdEmailAgent + prompt

**Files:**
- Create: `backend/agents/cold_email_agent.py`
- Create: `backend/prompts/cold_email.md`

- [ ] **Step 1: Create the prompt template `backend/prompts/cold_email.md`**

```markdown
# Cold Email Drafter

You are a professional cold email writer helping a job candidate reach out to contacts at target companies.

## Candidate Profile
{profile}

## Job Description
{jd}

## Contact
Name: {contact_name}
Title: {contact_title}

## Instructions

Draft a concise, professional cold email with four elements:
1. **Hook** — one specific, genuine thing about the company that you find compelling (extract from the JD: their product, tech stack, or culture signal — not generic praise)
2. **Who you are** — one sentence from the profile
3. **Why you're a fit** — two to three concrete points linking the candidate's background to the JD requirements
4. **Ask** — low-friction: request a 15-minute call or quick chat, not "please hire me"

If contact name is empty or missing, open with "Hi [Company] team,".
If contact title is empty or missing, omit any title-specific framing in the fit section.
Keep the email under 200 words. Friendly but professional tone.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"subject": "string", "body": "string"}
```

- [ ] **Step 2: Create `backend/agents/cold_email_agent.py`**

```python
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.schemas import ColdEmailOutput


class ColdEmailAgent(BaseAgent):
    async def run(
        self,
        profile: str,
        jd: str,
        contact_name: str | None,
        contact_title: str | None,
    ) -> ColdEmailOutput:
        template = self._load_prompt("cold_email")
        system = (
            template
            .replace("{profile}", profile)
            .replace("{jd}", jd)
            .replace("{contact_name}", contact_name or "")
            .replace("{contact_title}", contact_title or "")
        )
        raw = await self._call(system, jd)
        try:
            return ColdEmailOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"cold_email: {e}") from e
```

- [ ] **Step 3: Write a smoke test to verify agent structure**

Add to a new file `tests/test_agents/test_cold_email_agent.py`:

```python
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.agents.cold_email_agent import ColdEmailAgent
from backend.agents.job_parser import AgentError


@pytest.mark.asyncio
async def test_cold_email_agent_returns_output():
    agent = ColdEmailAgent()
    mock_response = '{"subject": "Excited about Stripe", "body": "Hi Alice,\\n\\nI loved..."}'

    with patch.object(agent, "_call", new=AsyncMock(return_value=mock_response)):
        result = await agent.run(
            profile="Software engineer with 5 years Python",
            jd="Stripe is hiring a backend engineer",
            contact_name="Alice Chen",
            contact_title="Engineering Manager",
        )

    assert result.subject == "Excited about Stripe"
    assert "Alice" in result.body


@pytest.mark.asyncio
async def test_cold_email_agent_handles_null_name_and_title():
    agent = ColdEmailAgent()
    mock_response = '{"subject": "Hello", "body": "Hi team, I noticed..."}'

    with patch.object(agent, "_call", new=AsyncMock(return_value=mock_response)):
        result = await agent.run(
            profile="Software engineer",
            jd="Company is hiring",
            contact_name=None,
            contact_title=None,
        )

    assert result.subject == "Hello"


@pytest.mark.asyncio
async def test_cold_email_agent_raises_on_bad_json():
    agent = ColdEmailAgent()

    with patch.object(agent, "_call", new=AsyncMock(return_value="not json at all")):
        with pytest.raises(AgentError):
            await agent.run("profile", "jd", "Name", "Title")
```

- [ ] **Step 4: Run agent tests**

```bash
python -m pytest tests/test_agents/test_cold_email_agent.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/cold_email_agent.py backend/prompts/cold_email.md tests/test_agents/test_cold_email_agent.py
git commit -m "feat: ColdEmailAgent with prompt template and tests"
```

---

### Task 5: Contacts API routes + register in main.py

**Files:**
- Create: `backend/routes/contacts.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing route tests first**

Create `tests/test_routes/test_contacts.py`:

```python
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from backend.models import Analysis, Contact, JobResult, Profile, User
from backend.services.auth_service import get_current_user


@pytest.fixture
def fake_user():
    return User(
        id="user-1", email="test@test.com", hashed_password="x",
        is_active=True, is_admin=False, created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def authed_client(app_client, fake_user):
    from backend.main import app
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def seeded_analysis(db_session):
    """Insert Profile, Analysis, JobResult(job_parser) with company='Stripe'."""
    profile = Profile(
        id="prof-1", yaml_data="", cv_text="", github_data="{}", merged_profile="test profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    analysis = Analysis(
        id="anal-1", jd_text="test jd", profile_id="prof-1",
        created_at=datetime.now(timezone.utc), partial=False,
    )
    db_session.add(analysis)
    jp = JobResult(
        id="jr-1", analysis_id="anal-1", agent_name="job_parser",
        output_json=json.dumps({"company": "Stripe", "required_skills": [],
                                "nice_to_have": [], "role_type": "Eng", "seniority": "Senior"}),
    )
    db_session.add(jp)
    await db_session.commit()
    return analysis


@pytest.mark.asyncio
async def test_list_contacts_requires_auth(app_client: AsyncClient):
    r = await app_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_contacts_empty(authed_client: AsyncClient, seeded_analysis):
    r = await authed_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_contacts_returns_sorted_by_confidence(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(Contact(
        id="c1", analysis_id="anal-1", email="low@stripe.com",
        confidence=0.3, status="discovered", source="hunter",
        created_at=datetime.now(timezone.utc),
    ))
    db_session.add(Contact(
        id="c2", analysis_id="anal-1", email="high@stripe.com",
        confidence=0.9, status="discovered", source="hunter",
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    r = await authed_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["email"] == "high@stripe.com"  # higher confidence first


@pytest.mark.asyncio
async def test_discover_requires_auth(app_client: AsyncClient):
    r = await app_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_discover_returns_contacts(authed_client: AsyncClient, seeded_analysis):
    mock_contacts = [
        Contact(id="c1", analysis_id="anal-1", email="alice@stripe.com",
                name="Alice Chen", title="EM", company="Stripe",
                source="hunter", confidence=0.9, status="discovered",
                created_at=datetime.now(timezone.utc)),
    ]
    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(return_value=mock_contacts),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["email"] == "alice@stripe.com"


@pytest.mark.asyncio
async def test_discover_503_on_unavailable(authed_client: AsyncClient, seeded_analysis):
    from backend.services.contact_discovery import ContactDiscoveryUnavailable
    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(side_effect=ContactDiscoveryUnavailable("Hunter.io down")),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_discover_422_on_domain_required(authed_client: AsyncClient, seeded_analysis):
    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(side_effect=ValueError("domain_required")),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_draft_404_on_missing_contact(authed_client: AsyncClient):
    r = await authed_client.post("/api/contacts/nonexistent/draft", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_draft_returns_subject_and_body(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(Contact(
        id="c1", analysis_id="anal-1", email="alice@stripe.com",
        name="Alice", title="EM", company="Stripe",
        source="hunter", confidence=0.9, status="discovered",
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    from backend.schemas import ColdEmailOutput
    mock_output = ColdEmailOutput(subject="Hi Alice", body="Dear Alice, ...")

    with patch("backend.routes.contacts.ColdEmailAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.with_tracking.return_value = instance
        instance.run = AsyncMock(return_value=mock_output)

        r = await authed_client.post("/api/contacts/c1/draft", json={})

    assert r.status_code == 200
    data = r.json()
    assert data["subject"] == "Hi Alice"
    assert data["body"] == "Dear Alice, ..."


@pytest.mark.asyncio
async def test_draft_500_on_agent_failure(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(Contact(
        id="c2", analysis_id="anal-1", email="bob@stripe.com",
        source="hunter", confidence=0.5, status="discovered",
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    from backend.agents.job_parser import AgentError

    with patch("backend.routes.contacts.ColdEmailAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.with_tracking.return_value = instance
        instance.run = AsyncMock(side_effect=AgentError("bad json"))

        r = await authed_client.post("/api/contacts/c2/draft", json={})

    assert r.status_code == 500


@pytest.mark.asyncio
async def test_send_400_when_no_draft(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(Contact(
        id="c3", analysis_id="anal-1", email="carol@stripe.com",
        source="hunter", confidence=0.6, status="discovered",
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    r = await authed_client.post("/api/contacts/c3/send", json={})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_send_idempotent_when_already_sent(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(Contact(
        id="c4", analysis_id="anal-1", email="dave@stripe.com",
        source="hunter", confidence=0.7, status="sent",
        draft_text="Hello Dave", sent_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    r = await authed_client.post("/api/contacts/c4/send", json={})
    assert r.status_code == 200
    assert r.json()["sent"] is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_routes/test_contacts.py -v 2>&1 | head -20
```

Expected: `ImportError` or 404s because the router isn't registered yet.

- [ ] **Step 3: Create `backend/routes/contacts.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.cold_email_agent import ColdEmailAgent
from backend.agents.job_parser import AgentError
from backend.database import get_db
from backend.models import Analysis, Contact, Profile
from backend.schemas import ContactRead, DiscoverRequest, DraftResponse, SendResponse
from backend.services.auth_service import get_current_user
from backend.services.contact_discovery import ContactDiscoveryUnavailable, discover_contacts
from backend.models import User

router = APIRouter(tags=["contacts"])


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    analysis_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRead]:
    result = await db.execute(
        select(Contact)
        .where(Contact.analysis_id == analysis_id)
        .order_by(Contact.confidence.desc(), Contact.created_at.asc())
    )
    return [ContactRead.model_validate(c) for c in result.scalars()]


@router.post("/contacts/discover", response_model=list[ContactRead])
async def discover(
    body: DiscoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactRead]:
    try:
        contacts = await discover_contacts(body.analysis_id, db, body.domain)
    except ContactDiscoveryUnavailable as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "contact_discovery_unavailable", "retry": True},
        ) from e
    except ValueError as e:
        if "domain_required" in str(e):
            raise HTTPException(status_code=422, detail={"error": "domain_required"})
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [ContactRead.model_validate(c) for c in contacts]


@router.post("/contacts/{contact_id}/draft", response_model=DraftResponse)
async def draft_email(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftResponse:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == contact.analysis_id))
    ).scalar_one()
    profile = (
        await db.execute(select(Profile).where(Profile.id == analysis.profile_id))
    ).scalar_one()

    agent = ColdEmailAgent().with_tracking(db, analysis_id=analysis.id)
    try:
        result = await agent.run(
            profile=profile.merged_profile,
            jd=analysis.jd_text,
            contact_name=contact.name,
            contact_title=contact.title,
        )
    except (AgentError, Exception) as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "draft_generation_failed"},
        ) from e

    contact.draft_subject = result.subject
    contact.draft_text = result.body
    contact.status = "drafted"
    await db.commit()
    return DraftResponse(subject=result.subject, body=result.body)


@router.post("/contacts/{contact_id}/send", response_model=SendResponse)
async def send_email(
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendResponse:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    if contact.status == "sent":
        return SendResponse(sent=True)

    if contact.draft_text is None:
        raise HTTPException(status_code=400, detail={"error": "draft_required"})

    # STUB: Gmail MCP integration not yet wired.
    # To wire: call mcp__claude_ai_Gmail__create_draft then send; update status on success.
    raise HTTPException(
        status_code=503,
        detail={"error": "gmail_unavailable", "retry": True},
    )
```

- [ ] **Step 4: Register the contacts router in `backend/main.py`**

Add import:
```python
from backend.routes.contacts import router as contacts_router
```

Add include after the metrics router line:
```python
app.include_router(contacts_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_routes/test_contacts.py -v
```

Expected: all 12 tests PASS. The `test_send_*` tests pass because 400 (no draft) and 200 (already sent) are handled before the 503 stub.

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
python -m pytest --tb=short -q
```

Expected: all tests PASS (existing cost monitoring + new contact tests).

- [ ] **Step 7: Commit**

```bash
git add backend/routes/contacts.py backend/main.py tests/test_routes/test_contacts.py
git commit -m "feat: contacts API routes (list, discover, draft, send) with tests"
```

---

### Task 6: Frontend — types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add `Contact` and `ColdEmailDraft` to `frontend/src/types/index.ts`**

Append to the end of the file (after the closing `}` of `CostSummary`):

```typescript
export interface Contact {
  id: string;
  analysis_id: string;
  email: string;
  name: string | null;
  title: string | null;
  company: string | null;
  source: string;
  confidence: number;
  status: "discovered" | "drafted" | "sent";
  draft_subject: string | null;
  draft_text: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface ColdEmailDraft {
  subject: string;
  body: string;
}
```

- [ ] **Step 2: Add 4 API methods to `frontend/src/api/client.ts`**

The `api` object currently ends at `getCostRuns`. Add four methods inside the `api` object, after `getCostRuns`:

```typescript
  getContacts: (analysisId: string) =>
    get<Contact[]>(`/contacts?analysis_id=${analysisId}`),
  discoverContacts: (analysisId: string, domain?: string) =>
    post<Contact[]>("/contacts/discover", { analysis_id: analysisId, domain: domain ?? null }),
  draftEmail: (contactId: string) =>
    post<ColdEmailDraft>(`/contacts/${contactId}/draft`, {}),
  sendEmail: (contactId: string) =>
    post<{ sent: boolean }>(`/contacts/${contactId}/send`, {}),
```

Also add a `post` helper before the `api` object (after the `get` function definition):

```typescript
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}
```

Add `Contact, ColdEmailDraft` to the import at line 1 of `client.ts`:

```typescript
import type { ProfileResponse, ProfileStatusResponse, GitHubRefreshResponse, AnalysisDetail, AgentName, SSECallbacks, DiscoveryRun, DiscoveryFeedResponse, User, AgentCost, RunCost, CostSummary, Contact, ColdEmailDraft } from "../types";
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add Contact/ColdEmailDraft types and cold email API methods"
```

---

### Task 7: Frontend — Cold Email tab in Results.tsx

**Files:**
- Modify: `frontend/src/pages/Results.tsx`

This task adds the "Cold Email" tab with a 3-screen flow to `Results.tsx`. The tab is only shown when `job_parser` output contains a non-empty `company` field.

- [ ] **Step 1: Add `Contact` import and expand the `Tab` type**

At the top of `Results.tsx`, add the `Contact` import:

```tsx
import type { AnalysisDetail, AgentName, AgentStatus, Contact } from "../types";
```

Change the `Tab` type and `TABS` array:

```tsx
type Tab = "score" | "gaps" | "resources" | "letter" | "resume" | "cold_email";
const TABS: { id: Tab; label: string }[] = [
  { id: "score", label: "Score" },
  { id: "gaps", label: "Gaps" },
  { id: "resources", label: "Resources" },
  { id: "letter", label: "Cover Letter" },
  { id: "resume", label: "Resume" },
  { id: "cold_email", label: "Cold Email" },
];
```

- [ ] **Step 2: Add Cold Email state variables inside the `Results` component**

Add these after the existing `useState` hooks:

```tsx
  // Cold Email state
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [originalDraftBody, setOriginalDraftBody] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [showSendModal, setShowSendModal] = useState(false);
  const [coldEmailScreen, setColdEmailScreen] = useState<"picker" | "review" | "sent">("picker");
  const [domainOverride, setDomainOverride] = useState("");
```

- [ ] **Step 3: Add tab mount effect for Cold Email**

Add a `useEffect` that loads contacts when the cold email tab is activated:

```tsx
  useEffect(() => {
    if (tab !== "cold_email" || !id) return;
    setContactsLoading(true);
    api.getContacts(id)
      .then((cs) => {
        setContacts(cs);
        // Derive screen from highest-status contact
        const sent = cs.find((c) => c.status === "sent");
        const drafted = cs.find((c) => c.status === "drafted");
        if (sent) {
          setColdEmailScreen("sent");
          setSelectedContactId(sent.id);
        } else if (drafted) {
          setColdEmailScreen("review");
          setSelectedContactId(drafted.id);
          setDraftSubject(drafted.draft_subject ?? "");
          setDraftBody(drafted.draft_text ?? "");
          setOriginalDraftBody(drafted.draft_text ?? "");
        } else {
          setColdEmailScreen("picker");
        }
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setContactsLoading(false));
  }, [tab, id]);
```

- [ ] **Step 4: Add helper functions for discover, draft, and send**

Add these inside the `Results` component after the `generate` function:

```tsx
  const handleDiscover = (domain?: string) => {
    if (!id) return;
    setContactsLoading(true);
    setContactsError(null);
    api.discoverContacts(id, domain || undefined)
      .then((cs) => {
        setContacts(cs);
        setColdEmailScreen("picker");
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setContactsLoading(false));
  };

  const handleDraft = () => {
    if (!selectedContactId) return;
    setDrafting(true);
    api.draftEmail(selectedContactId)
      .then((d) => {
        setDraftSubject(d.subject);
        setDraftBody(d.body);
        setOriginalDraftBody(d.body);
        setColdEmailScreen("review");
      })
      .catch((e) => setContactsError(String(e)))
      .finally(() => setDrafting(false));
  };

  const handleSendConfirm = () => {
    if (!selectedContactId) return;
    setSending(true);
    setShowSendModal(false);
    api.sendEmail(selectedContactId)
      .then(() => setColdEmailScreen("sent"))
      .catch((e) => setContactsError(String(e)))
      .finally(() => setSending(false));
  };
```

- [ ] **Step 5: Add the Cold Email tab panel**

The tab panel section starts at `<div className="pt-2">`. Add the cold_email case inside that div, after the `resume` block and before the closing `</div>`:

```tsx
        {tab === "cold_email" && (
          <div className="space-y-4">
            {contactsError && (
              <p className="text-sm text-red-600">{contactsError}</p>
            )}
            {contactsLoading && (
              <p className="text-sm text-slate-400">Loading…</p>
            )}

            {/* Screen 1 — Contact Picker */}
            {!contactsLoading && coldEmailScreen === "picker" && (
              <div className="space-y-4">
                {contacts.length === 0 ? (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-500">
                      No contacts discovered yet. Enter a company domain to search:
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="stripe.com"
                        value={domainOverride}
                        onChange={(e) => setDomainOverride(e.target.value)}
                        className="flex-1 border rounded px-3 py-2 text-sm"
                      />
                      <button
                        onClick={() => handleDiscover(domainOverride)}
                        className="px-4 py-2 bg-blue-600 text-white rounded text-sm"
                      >
                        Search
                      </button>
                    </div>
                    <button
                      onClick={() => handleDiscover()}
                      className="text-sm text-blue-600 underline"
                    >
                      Auto-detect from job description
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-600 font-medium">
                      Select a contact to email:
                    </p>
                    {contacts.map((c) => {
                      const badge =
                        c.confidence >= 0.8
                          ? { label: "High", cls: "bg-green-100 text-green-700" }
                          : c.confidence >= 0.5
                          ? { label: "Medium", cls: "bg-yellow-100 text-yellow-700" }
                          : { label: "Low", cls: "bg-slate-100 text-slate-600" };
                      return (
                        <label
                          key={c.id}
                          className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer ${
                            selectedContactId === c.id ? "border-blue-500 bg-blue-50" : ""
                          }`}
                        >
                          <input
                            type="radio"
                            name="contact"
                            value={c.id}
                            checked={selectedContactId === c.id}
                            onChange={() => setSelectedContactId(c.id)}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium">{c.name ?? c.email}</p>
                            {c.title && (
                              <p className="text-xs text-slate-500">{c.title}</p>
                            )}
                            <p className="text-xs text-slate-400">{c.email}</p>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.cls}`}>
                            {badge.label}
                          </span>
                        </label>
                      );
                    })}
                    <button
                      onClick={handleDraft}
                      disabled={!selectedContactId || drafting}
                      className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
                    >
                      {drafting ? "Drafting…" : "Draft Email"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Screen 2 — Draft Review */}
            {!contactsLoading && coldEmailScreen === "review" && (
              <div className="space-y-3">
                {drafting && (
                  <p className="text-sm text-slate-400">Drafting email (5–15s)…</p>
                )}
                {!drafting && (
                  <>
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Subject</label>
                      <input
                        type="text"
                        value={draftSubject}
                        onChange={(e) => setDraftSubject(e.target.value)}
                        className="w-full border rounded px-3 py-2 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Body</label>
                      <textarea
                        value={draftBody}
                        onChange={(e) => setDraftBody(e.target.value)}
                        rows={10}
                        className="w-full border rounded px-3 py-2 text-sm font-mono"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          if (draftBody !== originalDraftBody) {
                            if (!window.confirm("This will overwrite your edits. Continue?")) return;
                          }
                          handleDraft();
                        }}
                        className="px-4 py-2 border rounded text-sm text-slate-700 hover:bg-slate-50"
                      >
                        Re-draft
                      </button>
                      <button
                        onClick={() => setShowSendModal(true)}
                        disabled={sending}
                        className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
                      >
                        {sending ? "Sending…" : "Send"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Screen 3 — Sent Confirmation */}
            {!contactsLoading && coldEmailScreen === "sent" && (() => {
              const sentContact = contacts.find((c) => c.id === selectedContactId) ?? contacts.find((c) => c.status === "sent");
              return (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-green-800 font-medium text-sm">
                    ✓ Sent to {sentContact?.name ?? sentContact?.email ?? "contact"}
                    {sentContact?.email && sentContact?.name ? ` (${sentContact.email})` : ""}
                  </p>
                  {sentContact?.sent_at && (
                    <p className="text-xs text-green-600 mt-1">
                      {new Date(sentContact.sent_at).toLocaleString()}
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Send confirmation modal */}
            {showSendModal && (() => {
              const target = contacts.find((c) => c.id === selectedContactId);
              return (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
                  <div className="bg-white rounded-lg p-6 max-w-sm w-full shadow-xl space-y-4">
                    <p className="text-sm text-slate-800">
                      Send to <strong>{target?.email}</strong>? The email will land in Gmail Drafts
                      briefly before sending — you can delete it from there if you act fast.
                    </p>
                    <div className="flex gap-3 justify-end">
                      <button
                        onClick={() => setShowSendModal(false)}
                        className="px-4 py-2 text-sm border rounded text-slate-700"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSendConfirm}
                        className="px-4 py-2 text-sm bg-blue-600 text-white rounded"
                      >
                        Confirm Send
                      </button>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
```

- [ ] **Step 6: Conditionally show the Cold Email tab based on company field**

The Cold Email tab should only render if `job_parser` output has a non-empty `company`. Update the `TABS` rendering to filter:

```tsx
      <div className="flex gap-2 border-b">
        {TABS
          .filter((t) => t.id !== "cold_email" || !!r.job_parser?.company)
          .map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                tab === t.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}{t.id === "cold_email" && coldEmailScreen === "sent" ? " ✓" : ""}
            </button>
          ))}
      </div>
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Results.tsx
git commit -m "feat: Cold Email tab with 3-screen flow in Results page"
```

---

### Task 8: Full test suite + final verification

**Files:**
- Run tests only — no new files.

- [ ] **Step 1: Run full backend test suite**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python -m pytest --tb=short -q
```

Expected: all tests PASS, coverage ≥ 70%.

- [ ] **Step 2: Verify frontend builds without errors**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TypeScript or module errors.

- [ ] **Step 3: Verify migration runs cleanly**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
python scripts/migrate.py
```

Expected output includes `✓ contacts table ready` (or `contacts table ready` on a fresh DB that skipped steps 1–16 as not-exists).

- [ ] **Step 4: Commit final verification**

```bash
git add -p  # review and stage any stray changes
git commit -m "chore: verify cold email feature - all tests pass, build clean"
```

---

## Known Limitations (V1)

| Item | Note |
|---|---|
| Gmail send stubbed | Route returns 503; wire `mcp__claude_ai_Gmail__create_draft` + `send` when credentials available |
| Pattern-fill removed | Only verified Hunter.io emails stored; zero results shows domain input |
| Re-draft version history | Overwrites `draft_text` in place; no history |
| Hunter.io retry logic | No retry on 503; client retries via UI |
| `sent_at` not set | Send is stubbed so `sent_at` never gets populated; update alongside Gmail wiring |
