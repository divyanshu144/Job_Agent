# Job Board Scrapers (Reed + Adzuna) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Reed.co.uk and Adzuna job board sources to the discovery pipeline so `POST /api/discovery/run?source=reed` and `?source=adzuna` work alongside the existing `?source=hn`.

**Architecture:** Two new client modules (`reed_client.py`, `adzuna_client.py`) each export a single `fetch_X_jobs(keywords, location) -> list[RawJob]` function that mirrors `fetch_hn_jobs()`. The existing `_run_discovery_task` dispatches to the right client based on the `source` param; `_process_job` is parameterised with a `source_tag` (was hardcoded `"hn"`). API keys live in `config.py`/`.env` server-side only — the frontend only ever sees the string `"reed"` or `"adzuna"`.

**Tech Stack:** Python 3.11, httpx (already a dep), pydantic-settings (already a dep), pytest + AsyncMock.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `backend/config.py` | Add `reed_api_key`, `adzuna_app_id`, `adzuna_app_key` |
| Modify | `.env.example` | Stub the three new vars |
| Create | `backend/services/reed_client.py` | `fetch_reed_jobs(keywords, location) -> list[RawJob]` |
| Create | `backend/services/adzuna_client.py` | `fetch_adzuna_jobs(keywords, location) -> list[RawJob]` |
| Modify | `backend/services/discovery.py` | Parameterise source tag; dispatch Reed/Adzuna; derive keywords from profiles |
| Modify | `backend/routes/discovery.py` | Validate source against `{"hn", "reed", "adzuna"}` |
| Create | `tests/test_services/test_reed_client.py` | 4 tests for reed_client |
| Create | `tests/test_services/test_adzuna_client.py` | 4 tests for adzuna_client |
| Modify | `tests/test_routes/test_discovery_routes.py` | Add invalid-source 422 test |

---

## Task 1: Config + `.env.example`

**Files:**
- Modify: `backend/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add the three new fields to `Settings`**

Open `backend/config.py`. The full file after the change:

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
    database_url: str = "sqlite+aiosqlite:///./data/jobfit.db"
    api_prefix: str = "/api"
    cv_path: str = "data/cv.pdf"
    profile_yaml_path: str = "data/candidate_profile.yaml"
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    hunter_api_key: str = ""
    reed_api_key: str = ""        # reed.co.uk developer API key
    adzuna_app_id: str = ""       # adzuna.co.uk application ID
    adzuna_app_key: str = ""      # adzuna.co.uk application key


settings = Settings()
```

- [ ] **Step 2: Add stubs to `.env.example`**

Append to `.env.example`:

```
REED_API_KEY=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
```

- [ ] **Step 3: Verify settings load**

```bash
python -c "from backend.config import settings; print(settings.reed_api_key, settings.adzuna_app_id)"
```

Expected: ` ` (two empty strings, no exception).

- [ ] **Step 4: Commit**

```bash
git add backend/config.py .env.example
git commit -m "feat(config): add reed and adzuna API key settings"
```

---

## Task 2: Reed client

**Files:**
- Create: `backend/services/reed_client.py`
- Create: `tests/test_services/test_reed_client.py`

### Step 1: Write the failing tests first

- [ ] **Step 1: Create `tests/test_services/test_reed_client.py`**

```python
# tests/test_services/test_reed_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


async def test_fetch_reed_jobs_returns_empty_when_key_missing():
    """Returns [] immediately if reed_api_key is empty — no HTTP call made."""
    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = ""
        from backend.services.reed_client import fetch_reed_jobs
        jobs = await fetch_reed_jobs("python engineer", "london")
    assert jobs == []


async def test_fetch_reed_jobs_happy_path():
    """One result in first page, empty second page → one RawJob returned."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "jobId": 42,
            "jobTitle": "Senior Python Engineer",
            "employerName": "Acme Corp",
            "locationName": "London",
            "jobDescription": (
                "We need a Python engineer with FastAPI and PostgreSQL experience "
                "for our platform team. 5+ years required. Remote friendly."
            ),
            "jobUrl": "https://www.reed.co.uk/jobs/senior-python-engineer/42",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python engineer", "london")

    assert len(jobs) == 1
    assert jobs[0].source_id == "reed_42"
    assert "Senior Python Engineer" in jobs[0].raw_text
    assert "Acme Corp" in jobs[0].raw_text
    assert jobs[0].source_url == "https://www.reed.co.uk/jobs/senior-python-engineer/42"
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_reed_jobs_http_error_returns_empty():
    """HTTP error on first page → returns [] gracefully."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python", "")

    assert jobs == []


async def test_fetch_reed_jobs_skips_short_descriptions():
    """Jobs whose combined text is < 100 chars are dropped."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "jobId": 99,
            "jobTitle": "Dev",
            "employerName": "Co",
            "locationName": "London",
            "jobDescription": "Short.",  # combined raw_text will be < 100 chars
            "jobUrl": "https://www.reed.co.uk/jobs/dev/99",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python", "london")

    assert jobs == []
```

- [ ] **Step 2: Run tests — expect RED (module doesn't exist yet)**

```bash
pytest tests/test_services/test_reed_client.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'backend.services.reed_client'`

- [ ] **Step 3: Create `backend/services/reed_client.py`**

```python
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

REED_API = "https://www.reed.co.uk/api/1.0/search"
_MIN_TEXT_LEN = 100
_MAX_RESULTS = 200
_PER_PAGE = 100


async def fetch_reed_jobs(keywords: str, location: str) -> list[RawJob]:
    """Fetch up to 200 jobs from Reed.co.uk using the developer REST API.

    Returns [] immediately if ``settings.reed_api_key`` is empty so the
    discovery pipeline degrades gracefully when the key is not configured.
    """
    if not settings.reed_api_key:
        logger.warning("reed_api_key not configured; skipping Reed fetch")
        return []

    jobs: list[RawJob] = []
    auth = (settings.reed_api_key, "")  # Reed: API key as HTTP Basic username

    async with httpx.AsyncClient(timeout=30, auth=auth) as client:
        for skip in range(0, _MAX_RESULTS, _PER_PAGE):
            params: dict[str, Any] = {
                "keywords": keywords,
                "resultsToTake": _PER_PAGE,
                "resultsToSkip": skip,
            }
            if location:
                params["locationName"] = location
            try:
                resp = await client.get(REED_API, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Reed API error (skip=%d): %s", skip, exc)
                break

            results: list[dict[str, Any]] = resp.json().get("results", [])
            if not results:
                break

            for r in results:
                job_id = str(r.get("jobId", ""))
                if not job_id:
                    continue
                title = r.get("jobTitle", "")
                employer = r.get("employerName", "")
                loc = r.get("locationName", "")
                description = r.get("jobDescription", "")
                url = r.get("jobUrl", f"https://www.reed.co.uk/jobs/{job_id}")
                raw_text = f"{title} at {employer} ({loc})\n\n{description}".strip()
                if len(raw_text) < _MIN_TEXT_LEN:
                    continue
                jobs.append(
                    RawJob(
                        source_id=f"reed_{job_id}",
                        source_url=url,
                        raw_text=raw_text,
                        dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
                    )
                )

    return jobs
```

- [ ] **Step 4: Run tests — expect GREEN**

```bash
pytest tests/test_services/test_reed_client.py -v 2>&1 | tail -15
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/reed_client.py tests/test_services/test_reed_client.py
git commit -m "feat(discovery): add Reed.co.uk job board client"
```

---

## Task 3: Adzuna client

**Files:**
- Create: `backend/services/adzuna_client.py`
- Create: `tests/test_services/test_adzuna_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_adzuna_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


async def test_fetch_adzuna_jobs_returns_empty_when_creds_missing():
    """Returns [] immediately if adzuna_app_id or adzuna_app_key is empty."""
    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = ""
        mock_cfg.adzuna_app_key = "key"
        from backend.services.adzuna_client import fetch_adzuna_jobs
        jobs = await fetch_adzuna_jobs("python", "london")
    assert jobs == []


async def test_fetch_adzuna_jobs_happy_path():
    """One result on page 1, empty page 2 → one RawJob."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "id": "adzuna-123",
            "title": "Backend Engineer",
            "company": {"display_name": "TechCo"},
            "location": {"display_name": "London"},
            "description": (
                "We are looking for a backend engineer with Python, FastAPI, "
                "PostgreSQL, and AWS experience to join our product team. "
                "5+ years required. Remote-friendly within EU."
            ),
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/adzuna-123",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert len(jobs) == 1
    assert jobs[0].source_id == "adzuna_adzuna-123"
    assert "Backend Engineer" in jobs[0].raw_text
    assert "TechCo" in jobs[0].raw_text
    assert jobs[0].source_url == "https://www.adzuna.co.uk/jobs/details/adzuna-123"
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_adzuna_jobs_http_error_returns_empty():
    """HTTP error → returns [] gracefully."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert jobs == []


async def test_fetch_adzuna_jobs_skips_short_descriptions():
    """Jobs with combined text < 100 chars are dropped."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "id": "short-1",
            "title": "Dev",
            "company": {"display_name": "Co"},
            "location": {"display_name": "London"},
            "description": "Short.",
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/short-1",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib
            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert jobs == []
```

- [ ] **Step 2: Run tests — expect RED**

```bash
pytest tests/test_services/test_adzuna_client.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'backend.services.adzuna_client'`

- [ ] **Step 3: Create `backend/services/adzuna_client.py`**

```python
from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.services.hn_client import RawJob

logger = logging.getLogger(__name__)

ADZUNA_API = "https://api.adzuna.com/v1/api/jobs"
_MIN_TEXT_LEN = 100
_PER_PAGE = 50
_MAX_PAGES = 4   # up to 200 results per run
_COUNTRY = "gb"  # UK endpoint; change to "us" etc. for other regions


async def fetch_adzuna_jobs(keywords: str, location: str) -> list[RawJob]:
    """Fetch up to 200 jobs from Adzuna (UK) using the public REST API.

    Returns [] immediately if either ``adzuna_app_id`` or ``adzuna_app_key``
    is empty so the pipeline degrades gracefully when credentials are absent.
    """
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        logger.warning("adzuna credentials not configured; skipping Adzuna fetch")
        return []

    jobs: list[RawJob] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, _MAX_PAGES + 1):
            params: dict[str, Any] = {
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_app_key,
                "results_per_page": _PER_PAGE,
                "content-type": "application/json",
            }
            if keywords:
                params["what"] = keywords
            if location:
                params["where"] = location

            try:
                resp = await client.get(
                    f"{ADZUNA_API}/{_COUNTRY}/search/{page}", params=params
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Adzuna API error (page=%d): %s", page, exc)
                break

            results: list[dict[str, Any]] = resp.json().get("results", [])
            if not results:
                break

            for r in results:
                job_id = str(r.get("id", ""))
                if not job_id:
                    continue
                title = r.get("title", "")
                company_info: dict[str, Any] = r.get("company") or {}
                loc_info: dict[str, Any] = r.get("location") or {}
                company = company_info.get("display_name", "")
                loc = loc_info.get("display_name", "")
                description = r.get("description", "")
                url = r.get(
                    "redirect_url",
                    f"https://www.adzuna.co.uk/jobs/details/{job_id}",
                )
                raw_text = f"{title} at {company} ({loc})\n\n{description}".strip()
                if len(raw_text) < _MIN_TEXT_LEN:
                    continue
                jobs.append(
                    RawJob(
                        source_id=f"adzuna_{job_id}",
                        source_url=url,
                        raw_text=raw_text,
                        dedup_hash=hashlib.sha256(raw_text.encode()).hexdigest(),
                    )
                )

    return jobs
```

- [ ] **Step 4: Run tests — expect GREEN**

```bash
pytest tests/test_services/test_adzuna_client.py -v 2>&1 | tail -10
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/adzuna_client.py tests/test_services/test_adzuna_client.py
git commit -m "feat(discovery): add Adzuna job board client"
```

---

## Task 4: Wire clients into the discovery pipeline

**Files:**
- Modify: `backend/services/discovery.py`

Two changes:
1. `_process_job` — add `source_tag: str = "hn"` param; replace hardcoded `"hn"` strings.
2. `_run_discovery_task` — load profiles before fetching (to derive keywords/location); dispatch based on `source`.

- [ ] **Step 1: Update imports in `discovery.py`**

At the top of `backend/services/discovery.py`, replace the single `hn_client` import line:

```python
from backend.services.hn_client import RawJob, fetch_hn_jobs
```

with:

```python
from backend.services.adzuna_client import fetch_adzuna_jobs
from backend.services.hn_client import RawJob, fetch_hn_jobs
from backend.services.reed_client import fetch_reed_jobs
```

- [ ] **Step 2: Add `source_tag` parameter to `_process_job`**

Replace the current `_process_job` signature and the two hardcoded `"hn"` lines:

Current signature (line ~135):
```python
async def _process_job(
    db: AsyncSession,
    run_id: str,
    raw: RawJob,
    profiles: list[SearchProfile],
    profile: Any,
    compact: str,
) -> None:
```

New signature:
```python
async def _process_job(
    db: AsyncSession,
    run_id: str,
    raw: RawJob,
    profiles: list[SearchProfile],
    profile: Any,
    compact: str,
    source_tag: str = "hn",
) -> None:
```

Replace the dedup branch (lines ~147-153):
```python
    existing = (
        await db.execute(select(Job).where(Job.dedup_hash == raw.dedup_hash))
    ).scalar_one_or_none()
    if existing is not None:
        sources = json.loads(existing.sources)
        if "hn" not in sources:
            sources.append("hn")
            await db.execute(
                update(Job).where(Job.id == existing.id).values(sources=json.dumps(sources))
            )
            await db.commit()
        return
```

with:

```python
    existing = (
        await db.execute(select(Job).where(Job.dedup_hash == raw.dedup_hash))
    ).scalar_one_or_none()
    if existing is not None:
        sources = json.loads(existing.sources)
        if source_tag not in sources:
            sources.append(source_tag)
            await db.execute(
                update(Job).where(Job.id == existing.id).values(sources=json.dumps(sources))
            )
            await db.commit()
        return
```

Replace the new-job creation block (line ~157-158):
```python
    job = Job(
        sources='["hn"]',
```

with:

```python
    job = Job(
        sources=json.dumps([source_tag]),
```

- [ ] **Step 3: Update `_run_discovery_task` to load profiles first and dispatch**

Replace the entire `_run_discovery_task` function:

```python
async def _run_discovery_task(run_id: str, source: str) -> None:
    # Background task — must own its own session (cannot receive FastAPI DI)
    # Phase 1: setup — load profiles, build compact profile, fetch jobs
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(status="running")
            )
            await db.commit()

            # Load search profiles first so Reed/Adzuna can use target_roles as keywords
            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            compact = build_compact_profile(profile.yaml_data, profile.cv_text)

            # Derive keyword string and primary location from configured search profiles
            all_roles = [r for p in profiles for r in p.target_roles]
            keywords = " ".join(all_roles[:3]) if all_roles else "software engineer"
            all_locations = [loc for p in profiles for loc in p.allowed_locations]
            location = all_locations[0] if all_locations else ""

            if source == "reed":
                raw_jobs = await fetch_reed_jobs(keywords, location)
            elif source == "adzuna":
                raw_jobs = await fetch_adzuna_jobs(keywords, location)
            else:  # "hn" — fetches the monthly "Who is Hiring" thread; no keywords needed
                raw_jobs = await fetch_hn_jobs()

            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(jobs_found=len(raw_jobs))
            )
            await db.commit()
    except Exception as e:
        logger.error("Discovery run %s setup failed: %s", run_id, e, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(
                update(DiscoveryRun)
                .where(DiscoveryRun.id == run_id)
                .values(status="failed", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
        return

    # Phase 2: process jobs concurrently, each with its own session
    sem = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _bounded(raw: RawJob) -> None:
        async with sem:
            async with SessionLocal() as db:
                await _process_job(
                    db, run_id, raw, profiles, profile, compact, source_tag=source
                )

    await asyncio.gather(*[_bounded(raw) for raw in raw_jobs], return_exceptions=True)

    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(
                status="complete",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
```

- [ ] **Step 4: Run existing discovery service tests — they must still pass**

```bash
pytest tests/test_services/test_discovery.py -v 2>&1 | tail -15
```

Expected: `6 passed` (no changes to existing tests needed — `source_tag="hn"` default preserves backward compatibility).

- [ ] **Step 5: Commit**

```bash
git add backend/services/discovery.py
git commit -m "feat(discovery): dispatch Reed/Adzuna; parameterise source_tag in _process_job"
```

---

## Task 5: Route validation + test

**Files:**
- Modify: `backend/routes/discovery.py`
- Modify: `tests/test_routes/test_discovery_routes.py`

- [ ] **Step 1: Write the failing test first**

Append to `tests/test_routes/test_discovery_routes.py`:

```python
async def test_trigger_discovery_invalid_source_returns_422(app_client):
    """Unknown source strings are rejected before any DB write."""
    resp = await app_client.post("/api/discovery/run?source=linkedin")
    assert resp.status_code == 422
    assert "linkedin" in resp.json()["detail"]
```

- [ ] **Step 2: Run the test — expect RED**

```bash
pytest tests/test_routes/test_discovery_routes.py::test_trigger_discovery_invalid_source_returns_422 -v
```

Expected: `FAILED` — currently the route accepts any string and passes it to `run_discovery`.

- [ ] **Step 3: Add `_VALID_SOURCES` guard to the route**

In `backend/routes/discovery.py`, add after the imports:

```python
_VALID_SOURCES = {"hn", "reed", "adzuna"}
```

Replace the `trigger_discovery` route handler:

```python
@router.post("/discovery/run")
async def trigger_discovery(
    source: str = Query(default="hn"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if source not in _VALID_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid source '{source}'. "
                f"Must be one of: {sorted(_VALID_SOURCES)}"
            ),
        )
    run_id = await run_discovery(source, db)
    return {"run_id": run_id}
```

- [ ] **Step 4: Run the new test — expect GREEN**

```bash
pytest tests/test_routes/test_discovery_routes.py::test_trigger_discovery_invalid_source_returns_422 -v
```

Expected: `PASSED`

- [ ] **Step 5: Run all discovery route tests**

```bash
pytest tests/test_routes/test_discovery_routes.py -v 2>&1 | tail -10
```

Expected: `6 passed` (5 existing + 1 new).

- [ ] **Step 6: Commit**

```bash
git add backend/routes/discovery.py tests/test_routes/test_discovery_routes.py
git commit -m "feat(discovery): validate source param; accept hn|reed|adzuna only"
```

---

## Task 6: Final check

- [ ] **Step 1: Run `make check`**

```bash
make check
```

Expected: all tests pass (including the 8 new ones for reed + adzuna clients and the source validation test), lint clean, mypy clean, coverage ≥ 70%.

If `mypy` flags the nested dict access in `adzuna_client.py`, verify that `company_info` and `loc_info` are typed as `dict[str, Any]` (they are in the implementation above).

- [ ] **Step 2: Commit the final state if not already committed**

All changes should already be committed by this point. If anything remains:

```bash
git add -A
git commit -m "chore: make check clean after job board scrapers"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| `reed_api_key`, `adzuna_app_id`, `adzuna_app_key` in `config.py` | Task 1 |
| Keys in `.env.example`, server-side only | Task 1 |
| `fetch_reed_jobs(keywords, location) -> list[RawJob]` | Task 2 |
| Reed: Basic auth, paginate, dedup_hash sha256, skip short | Task 2 |
| Reed degrades gracefully when key missing | Task 2 |
| `fetch_adzuna_jobs(keywords, location) -> list[RawJob]` | Task 3 |
| Adzuna: app_id/key as query params, paginate, skip short | Task 3 |
| Adzuna degrades gracefully when creds missing | Task 3 |
| `_process_job` `source_tag` param replaces hardcoded `"hn"` | Task 4 |
| `_run_discovery_task` dispatches on `source` | Task 4 |
| Keywords derived from `search_profiles.target_roles` | Task 4 |
| Location derived from `search_profiles.allowed_locations` | Task 4 |
| Route rejects unknown source strings with 422 | Task 5 |
| All existing tests still pass | Task 4 (default `source_tag="hn"`) |
| `make check` green end-to-end | Task 6 |

### Placeholder scan

No TBDs, no "similar to above", all code blocks complete. ✓

### Type consistency

- `RawJob` imported from `hn_client` in both new clients — same type in `_process_job`. ✓
- `source_tag: str = "hn"` default — existing callers unchanged. ✓
- `fetch_reed_jobs(keywords: str, location: str)` / `fetch_adzuna_jobs(keywords: str, location: str)` — both called in `_run_discovery_task` with `(keywords, location)` positional args. ✓
- `company_info: dict[str, Any]` and `loc_info: dict[str, Any]` typed explicitly in adzuna_client — mypy clean. ✓
