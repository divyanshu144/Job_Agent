# Job Discovery — Design Spec

**Date:** 2026-05-24
**Status:** Approved for implementation planning

---

## Goal

Automatically fetch jobs from external sources, run them through the existing 6-agent match pipeline, and surface good matches to the user — without the user having to paste job descriptions manually. The manual paste flow must remain unchanged.

---

## Architecture Overview

A `discovery` service layer sits alongside the existing `orchestrator`. It owns fetch → filter → score. The route is a thin trigger. The same service function can be called by a scheduler later with zero refactoring.

```
POST /api/discovery/run
  → creates DiscoveryRun row (status=pending)
  → asyncio.create_task(_run_discovery_task)
  → returns run_id immediately

_run_discovery_task (background, own DB session)
  → fetch raw jobs from source (HN Algolia API)
  → for each job:
      dedup check (skip if dedup_hash exists, append source)
      Stage 1: keyword filter (Python, zero cost)
      Stage 2: Haiku call → relevant + title/company/location
      Phase 1: _run_phase1(jd, profile, db, job_id=job.id)
  → update DiscoveryRun.status = complete | failed

Frontend
  → polls GET /api/discovery/runs/{run_id} every 3s
  → stops polling on terminal status (complete | failed)
  → fetches feed immediately on completion
  → user clicks "Generate Documents" → existing Phase 2 route → existing Results page
```

---

## Data Model

### New table: `jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `sources` | TEXT | JSON list: `["hn"]`, appended when same hash found on second source |
| `source_id` | TEXT | Primary source's native ID (HN comment objectID) |
| `source_url` | TEXT | Direct link to original posting |
| `title` | TEXT | Extracted by Stage 2 Haiku |
| `company` | TEXT | Extracted by Stage 2 Haiku |
| `location` | TEXT nullable | Extracted by Stage 2 Haiku |
| `raw_text` | TEXT | Full JD text as fetched |
| `dedup_hash` | TEXT UNIQUE | `sha256(raw_text)`, globally unique across all sources |
| `discovered_at` | DATETIME | |
| `state` | TEXT | `discovered \| filtered \| scored \| analyzed` |
| `relevance_score` | INT nullable | From `match_scorer`, null until Phase 1 runs |
| `matched_profiles` | TEXT | JSON list of search profile names that meet `min_score` |
| `discovery_run_id` | TEXT FK → `discovery_runs` | |

No `analysis_id` on `jobs`. The FK lives on `analyses.job_id`. Feed queries use a LEFT JOIN to retrieve `analysis_id`.

### New table: `discovery_runs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `source` | TEXT | `"hn"` \| `"watchlist"` \| `"wellfound"` \| `"rss"` |
| `triggered_by` | TEXT | `"manual"` \| `"scheduler"` |
| `status` | TEXT | `pending \| running \| complete \| failed` |
| `started_at` | DATETIME | |
| `completed_at` | DATETIME nullable | |
| `jobs_found` | INT | Default 0, updated in real time |
| `jobs_passed_stage1` | INT | Default 0, updated in real time |
| `jobs_passed_stage2` | INT | Default 0, updated in real time |
| `jobs_scored` | INT | Default 0, updated in real time |

### Modified: `analyses`

Add one nullable column:

```sql
ALTER TABLE analyses ADD COLUMN job_id TEXT REFERENCES jobs(id);
```

Null for all existing manual-paste analyses. Set to `job.id` when `_run_phase1` is called from discovery.

### Migration

`scripts/migrate.py` gets two new steps:
1. `CREATE TABLE IF NOT EXISTS jobs (...)` with all columns and `UNIQUE(dedup_hash)`
2. `CREATE TABLE IF NOT EXISTS discovery_runs (...)` with all columns
3. `ALTER TABLE analyses ADD COLUMN job_id TEXT REFERENCES jobs(id)` (idempotent with duplicate-column guard)

---

## Search Profiles

Defined in `data/candidate_profile.yaml`:

```yaml
search_profiles:
  - name: AI-focused
    target_roles: [Backend Engineer, ML Engineer]
    min_score: 65
  - name: Broad search
    target_roles: [Backend, Fullstack, DevOps, Data Engineer]
    min_score: 50
```

Loaded once at the top of `_run_discovery_task`, passed into each `_process_job` call. Not re-read per job.

**Stage 1** uses the union of all `target_roles` across all profiles as the keyword set.

**Post-Phase 1** checks `relevance_score` against each profile's `min_score`. `matched_profiles` is the JSON list of profile names the job satisfies.

---

## Service Architecture

### New: `backend/services/hn_client.py`

Single responsibility: Algolia HN API → `list[RawJob]`. No filtering, no scoring.

```python
@dataclass
class RawJob:
    source_id: str    # HN comment objectID
    source_url: str   # https://news.ycombinator.com/item?id=...
    raw_text: str     # HTML-stripped comment text
    dedup_hash: str   # sha256(raw_text)

async def fetch_hn_jobs() -> list[RawJob]: ...
```

Finds the current month's "Ask HN: Who is Hiring?" thread via Algolia search, fetches all top-level comments, strips HTML, returns `RawJob` list.

### New: `backend/services/discovery.py`

```python
# Public entry point — route OR scheduler calls this
async def run_discovery(source: str, db: AsyncSession) -> str:
    run = DiscoveryRun(source=source, triggered_by="manual", status="pending", ...)
    db.add(run); await db.commit()
    asyncio.create_task(_run_discovery_task(run.id, source))
    return run.id

# Background task — owns its own DB session
async def _run_discovery_task(run_id: str, source: str) -> None:
    async with SessionLocal() as db:
        await _update_run(db, run_id, status="running")
        try:
            raw_jobs = await fetch_hn_jobs()
            await _update_run(db, run_id, jobs_found=len(raw_jobs))
            profiles = _load_search_profiles()
            profile = await get_or_build_profile(db)
            for raw in raw_jobs:
                await _process_job(db, run_id, raw, profiles, profile)
            await _update_run(db, run_id, status="complete", completed_at=utcnow())
        except Exception as e:
            logger.error(f"Discovery run {run_id} failed: {e}", exc_info=True)
            await _update_run(db, run_id, status="failed", completed_at=utcnow())

async def _process_job(db, run_id, raw, profiles, profile) -> None:
    # 1. Dedup: if hash exists, append source and return
    existing = await _find_by_hash(db, raw.dedup_hash)
    if existing:
        await _append_source(db, existing, "hn"); return

    # 2. Create job row and commit immediately (so filtered jobs persist)
    job = Job(sources='["hn"]', state="discovered", ...)
    db.add(job); await db.flush(); await db.commit()

    # 3. Stage 1: keyword filter (pure Python)
    all_roles = {r for p in profiles for r in p.target_roles}
    if not any(role.lower() in raw.raw_text.lower() for role in all_roles):
        job.state = "filtered"; await db.commit(); return
    await _increment_run(db, run_id, "jobs_passed_stage1")

    # 4. Stage 2: Haiku relevance + metadata extraction
    s2 = await _stage2_check(raw.raw_text, profile)
    job.title = s2.title; job.company = s2.company; job.location = s2.location
    if not s2.relevant:
        job.state = "filtered"; await db.commit(); return
    await _increment_run(db, run_id, "jobs_passed_stage2")

    # 5. Phase 1: full evaluate pipeline (reuses orchestrator)
    result = await _run_phase1(raw.raw_text, profile, db, job_id=job.id)
    job.relevance_score = result.score
    job.matched_profiles = json.dumps(_match_profiles(result.score, profiles))
    job.state = "scored"; await db.commit()
    await _increment_run(db, run_id, "jobs_scored")
```

**Stage 2 Haiku prompt returns:**
```json
{"relevant": true, "reason": "...", "title": "Backend Engineer", "company": "Stripe", "location": "Remote"}
```

### Refactored: `backend/services/orchestrator.py`

Extract Phase 1 agent calls into a pure function:

```python
@dataclass
class Phase1Result:
    analysis_id: str
    score: int
    partial: bool
    prior: PriorOutputs

async def _run_phase1(
    jd: str,
    profile: Profile,
    db: AsyncSession,
    job_id: str | None = None,   # set by discovery, None for manual flow
) -> Phase1Result:
    # Runs job_parser → match_scorer → gap_analyst
    # Saves Analysis(evaluate_only=True, job_id=job_id) + JobResult rows
    # Returns Phase1Result — no SSE, no yielding

async def run_evaluate_pipeline(
    jd: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    # Cache check (unchanged)
    # Calls _run_phase1(jd, profile, db, job_id=None)
    # Wraps Phase1Result in SSE events
    # ~20 lines, thin wrapper
```

`run_generate_pipeline` is untouched.

### Modified: `backend/main.py`

Startup lifespan resets stale running discovery runs:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.status == "running")
            .values(status="failed", completed_at=utcnow())
        )
        await db.commit()
    yield
```

Register discovery router with `prefix=settings.api_prefix`.

---

## API Routes

### New: `backend/routes/discovery.py`

```
POST /api/discovery/run?source=hn
  Body: none
  Returns: {"run_id": "..."}
  Effect: creates DiscoveryRun, spawns background task

GET /api/discovery/runs/{run_id}
  Returns: DiscoveryRunResponse

GET /api/discovery/runs
  Returns: list[DiscoveryRunResponse]  (most recent first, limit 20)

GET /api/discovery/feed?profile=AI-focused&min_score=65&limit=50&offset=0
  Returns: DiscoveryFeedResponse
```

### Schemas

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
    status: str           # pending | running | complete | failed
    started_at: datetime
    completed_at: datetime | None
    funnel: FunnelMetrics

class DiscoveryFeedItem(BaseModel):
    id: str
    title: str
    company: str
    location: str | None
    sources: list[str]         # parsed from JSON
    relevance_score: int
    matched_profiles: list[str]  # parsed from JSON
    analysis_id: str           # from LEFT JOIN on analyses.job_id
    state: str
    discovered_at: datetime

class DiscoveryFeedResponse(BaseModel):
    items: list[DiscoveryFeedItem]
    total: int
    has_more: bool
```

**Feed SQL:**
```sql
SELECT jobs.*, analyses.id AS analysis_id
FROM jobs
LEFT JOIN analyses ON analyses.job_id = jobs.id
WHERE jobs.state = 'scored'
  AND jobs.relevance_score >= :min_score
  AND jobs.matched_profiles LIKE :profile_filter  -- JSON contains check
ORDER BY jobs.relevance_score DESC
LIMIT :limit OFFSET :offset
```

---

## Frontend

### New: `frontend/src/pages/Discover.tsx`

Three UI states:

**Idle:** "Last fetched: 3 days ago" + "Fetch HN Jobs" button. Reads `GET /api/discovery/runs` for last run timestamp.

**Running:** Button disabled. Live funnel counter, updated every 3 seconds:
```
Fetching HN jobs...
487 found → 52 passed keyword filter → 19 passed relevance → 19 scored ✓
```

Polling stops when `status === 'complete' || status === 'failed'`. On completion, `fetchFeed()` is called immediately.

**Feed:** Sorted by score descending. Filter bar: search profile dropdown, min score slider (default from profile's `min_score`). Pagination with "Load more" when `has_more === true`.

Each job card:
```
[87%]  Backend Engineer · Stripe · Remote     [AI-focused] [Broad]
[74%]  Full Stack Engineer · Linear · London  [Broad]
                                   [Generate Documents ↗]
```

"Generate Documents" calls existing `POST /api/analyse/generate/{analysis_id}` → SSE stream → navigate to `/results/{analysis_id}`. Results page is completely unchanged.

### Modified: `frontend/src/App.tsx`

Add `/discover` route + "Discover" nav item alongside existing nav.

### New types: `frontend/src/types/index.ts`

```typescript
interface FunnelMetrics {
  jobs_found: number;
  passed_stage1: number;
  passed_stage2: number;
  scored: number;
}

interface DiscoveryRun {
  id: string;
  source: string;
  triggered_by: string;
  status: "pending" | "running" | "complete" | "failed";
  started_at: string;
  completed_at: string | null;
  funnel: FunnelMetrics;
}

interface DiscoveryFeedItem {
  id: string;
  title: string;
  company: string;
  location: string | null;
  sources: string[];
  relevance_score: number;
  matched_profiles: string[];
  analysis_id: string;
  state: string;
  discovered_at: string;
}

interface DiscoveryFeedResponse {
  items: DiscoveryFeedItem[];
  total: number;
  has_more: boolean;
}
```

### New methods: `frontend/src/api/client.ts`

```typescript
triggerDiscovery(source: string): Promise<{ run_id: string }>
getDiscoveryRun(runId: string): Promise<DiscoveryRun>
getDiscoveryRuns(): Promise<DiscoveryRun[]>
getDiscoveryFeed(params: { profile?: string; minScore?: number; limit?: number; offset?: number }): Promise<DiscoveryFeedResponse>
```

---

## Out of Scope (Phase A)

- APScheduler / automatic scheduling (designed for, not built)
- Watchlist, Wellfound, RSS sources (HN only)
- Cross-source fuzzy deduplication (exact hash only)
- Concurrent job processing (sequential per run)
- Auto-apply or any submission automation

---

## Source Extensibility

Adding a new source later requires:
1. A new `fetch_<source>_jobs() -> list[RawJob]` function
2. One branch in `_run_discovery_task` routing `source` to the right fetcher
3. Zero changes to the funnel, filter, Phase 1, or frontend

The `RawJob` dataclass is the interface contract between sources and the funnel.
