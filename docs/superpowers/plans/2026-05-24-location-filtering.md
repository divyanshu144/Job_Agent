# Location Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter discovery jobs by geographic location at Stage 2 (pipeline-level) to avoid wasting Phase 1 Haiku calls on jobs outside the team's target regions, and add a location text filter on the Discover feed UI.

**Architecture:** After Stage 2 Haiku extracts the `location` field, a new `_location_allowed()` function checks it against `allowed_locations` in each search profile. "Remote" always passes. If no profile has `allowed_locations`, all locations are allowed. The feed endpoint also gains a `?location=` query param for post-hoc UI filtering.

**Tech Stack:** Python (backend filter logic), YAML config, FastAPI query param, React text input.

---

## File Map

| File | Change |
|---|---|
| `backend/services/discovery.py` | Add `allowed_locations` to `SearchProfile`; add `_location_allowed()`; call it in `_process_job` after Stage 2 |
| `data/candidate_profile.yaml` | Add `allowed_locations` to each `search_profile` block |
| `backend/routes/discovery.py` | Add `location: str \| None` query param to `get_discovery_feed` |
| `frontend/src/pages/Discover.tsx` | Add location text input next to profile filter |
| `frontend/src/api/client.ts` | Pass `location` param to `getDiscoveryFeed` |
| `tests/test_services/test_discovery_location.py` | Unit tests for `_location_allowed` |

---

### Task 1: `_location_allowed` logic + SearchProfile update

**Files:**
- Modify: `backend/services/discovery.py`
- Create: `tests/test_services/test_discovery_location.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_discovery_location.py
import pytest
from backend.services.discovery import SearchProfile, _location_allowed

@pytest.fixture
def profiles_uk_europe():
    return [
        SearchProfile(
            name="AI",
            target_roles=["ML Engineer"],
            allowed_locations=["UK", "Europe", "Remote", "London", "Berlin", "Amsterdam", "Dublin"],
            min_score=65,
        )
    ]

@pytest.fixture
def profiles_no_restriction():
    return [SearchProfile(name="Any", target_roles=["Engineer"], allowed_locations=[], min_score=50)]

def test_none_location_allowed(profiles_uk_europe):
    assert _location_allowed(None, profiles_uk_europe) is True

def test_remote_always_allowed(profiles_uk_europe):
    assert _location_allowed("Remote (US-based)", profiles_uk_europe) is True
    assert _location_allowed("Fully Remote", profiles_uk_europe) is True

def test_uk_location_allowed(profiles_uk_europe):
    assert _location_allowed("London, UK", profiles_uk_europe) is True
    assert _location_allowed("London / Remote", profiles_uk_europe) is True

def test_europe_location_allowed(profiles_uk_europe):
    assert _location_allowed("Berlin, Germany", profiles_uk_europe) is True
    assert _location_allowed("Amsterdam", profiles_uk_europe) is True

def test_us_only_rejected(profiles_uk_europe):
    assert _location_allowed("San Francisco, CA", profiles_uk_europe) is False
    assert _location_allowed("New York (US only)", profiles_uk_europe) is False

def test_no_restriction_allows_all(profiles_no_restriction):
    assert _location_allowed("San Francisco", profiles_no_restriction) is True

def test_empty_location_string_allowed(profiles_uk_europe):
    assert _location_allowed("", profiles_uk_europe) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent
pytest tests/test_services/test_discovery_location.py -v 2>&1 | head -30
```
Expected: ImportError or AttributeError — `_location_allowed` doesn't exist yet.

- [ ] **Step 3: Update `SearchProfile` and add `_location_allowed` in discovery.py**

In `backend/services/discovery.py`, change the `SearchProfile` dataclass and add the function:

```python
@dataclass
class SearchProfile:
    name: str
    target_roles: list[str]
    allowed_locations: list[str]   # new field — empty means no restriction
    min_score: int


def _location_allowed(location: str | None, profiles: list[SearchProfile]) -> bool:
    """Return True if the job location is acceptable to any search profile.

    Rules:
    - None or empty string → allow (no location stated, don't reject)
    - Contains "remote" anywhere → always allow
    - Otherwise: at least one profile must have an allowed_locations entry
      that appears as a substring in the location string (case-insensitive).
    - A profile with empty allowed_locations imposes no restriction.
    """
    if not location:
        return True
    loc = location.lower()
    if "remote" in loc:
        return True
    for p in profiles:
        if not p.allowed_locations:
            return True  # profile with no restriction = allow all
        for allowed in p.allowed_locations:
            if allowed.lower() in loc:
                return True
    return False
```

Also update `_load_search_profiles()` to read the new field:

```python
def _load_search_profiles() -> list[SearchProfile]:
    try:
        text = Path(settings.profile_yaml_path).read_text()
        data = yaml.safe_load(text)
        return [
            SearchProfile(
                name=p["name"],
                target_roles=p["target_roles"],
                allowed_locations=p.get("allowed_locations", []),
                min_score=p["min_score"],
            )
            for p in data.get("search_profiles", [])
        ]
    except Exception:
        return []
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_services/test_discovery_location.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/discovery.py tests/test_services/test_discovery_location.py
git commit -m "feat: add location filtering logic to discovery service"
```

---

### Task 2: Apply location filter in `_process_job` + update YAML

**Files:**
- Modify: `backend/services/discovery.py` (`_process_job` function)
- Modify: `data/candidate_profile.yaml`

- [ ] **Step 1: Add `allowed_locations` to YAML search profiles**

In `data/candidate_profile.yaml`, update the `search_profiles` block:

```yaml
search_profiles:
  - name: AI-focused
    target_roles:
      - ML Engineer
      - AI Engineer
      - Machine Learning Engineer
      - LLM Engineer
      - Backend Engineer
      - Python Engineer
    allowed_locations:
      - UK
      - United Kingdom
      - Europe
      - Remote
      - London
      - Berlin
      - Amsterdam
      - Dublin
      - Paris
      - Barcelona
      - Stockholm
      - Copenhagen
    min_score: 65
  - name: Broad search
    target_roles:
      - Backend
      - Fullstack
      - Full Stack
      - Data Engineer
      - Software Engineer
      - DevOps
    allowed_locations:
      - UK
      - United Kingdom
      - Europe
      - Remote
      - London
      - Berlin
      - Amsterdam
      - Dublin
      - Paris
      - Barcelona
      - Stockholm
      - Copenhagen
    min_score: 50
```

- [ ] **Step 2: Add location filter call in `_process_job` after Stage 2**

In `backend/services/discovery.py`, find the block after `s2.relevant` check and add location filtering. The full block after Stage 2 becomes:

```python
    await db.execute(
        update(Job).where(Job.id == job.id).values(
            title=s2.title, company=s2.company, location=s2.location
        )
    )
    await db.commit()

    if not s2.relevant or not _location_allowed(s2.location, profiles):
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
```

This replaces the existing block that only checked `if not s2.relevant`.

- [ ] **Step 3: Verify logic by running the full test suite**

```bash
pytest tests/ -v --ignore=tests/test_routes/test_status.py 2>&1 | tail -20
```
Expected: existing tests still pass; new location tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/services/discovery.py data/candidate_profile.yaml
git commit -m "feat: apply location filter in discovery pipeline after Stage 2"
```

---

### Task 3: Feed location filter (backend + frontend)

**Files:**
- Modify: `backend/routes/discovery.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Discover.tsx`

- [ ] **Step 1: Add `location` query param to `get_discovery_feed`**

In `backend/routes/discovery.py`, update the `get_discovery_feed` function signature and query:

```python
@router.get("/discovery/feed", response_model=DiscoveryFeedResponse)
async def get_discovery_feed(
    profile: str | None = Query(default=None),
    location: str | None = Query(default=None),
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
        base = base.where(Job.matched_profiles.like(f'%"{profile}"%'))
    if location:
        base = base.where(Job.location.ilike(f"%{location}%"))

    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))
    ).all()

    return DiscoveryFeedResponse(
        items=[_job_row_to_item(r) for r in rows],
        total=total,
        has_more=offset + limit < total,
    )
```

- [ ] **Step 2: Update `getDiscoveryFeed` in `frontend/src/api/client.ts`**

```typescript
  getDiscoveryFeed: (params: { profile?: string; location?: string; minScore?: number; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.profile) q.set("profile", params.profile);
    if (params.location) q.set("location", params.location);
    if (params.minScore !== undefined) q.set("min_score", String(params.minScore));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return get<DiscoveryFeedResponse>(`/discovery/feed${qs ? "?" + qs : ""}`);
  },
```

- [ ] **Step 3: Add location filter input to `Discover.tsx`**

In `frontend/src/pages/Discover.tsx`, add `locationFilter` state and update the filter row. Replace the filters section:

```typescript
  const [locationFilter, setLocationFilter] = useState("");

  // update loadFeed signature and calls:
  const loadFeed = useCallback(async (profile?: string, location?: string) => {
    const res = await api.getDiscoveryFeed({ profile: profile || undefined, location: location || undefined });
    setFeed(res.items);
    setTotal(res.total);
  }, []);

  // update handleProfileFilter:
  function handleProfileFilter(value: string) {
    setProfileFilter(value);
    loadFeed(value || undefined, locationFilter || undefined);
  }

  // add location handler:
  function handleLocationFilter(value: string) {
    setLocationFilter(value);
    loadFeed(profileFilter || undefined, value || undefined);
  }
```

And in the JSX, update the filter row to include a location input:

```tsx
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-slate-500">
              <strong className="text-slate-700">{total}</strong> matched job{total !== 1 ? "s" : ""}
            </p>
            <div className="flex gap-2 items-center">
              <input
                type="text"
                value={locationFilter}
                onChange={(e) => handleLocationFilter(e.target.value)}
                placeholder="Filter by location…"
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 w-44"
              />
              {allProfiles.length > 1 && (
                <select
                  value={profileFilter}
                  onChange={(e) => handleProfileFilter(e.target.value)}
                  className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                >
                  <option value="">All profiles</option>
                  {allProfiles.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
```

Also update the polling `loadFeed` call to pass current filters:

```typescript
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
        if (run.status === "complete") loadFeed(profileFilter || undefined, locationFilter || undefined);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeRunId, profileFilter, locationFilter, loadFeed]);
```

- [ ] **Step 4: Verify backend with curl**

```bash
curl -s "http://localhost:8000/api/discovery/feed?location=London" | python3 -m json.tool | head -20
```
Expected: only jobs with "London" in their location field.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/discovery.py frontend/src/api/client.ts frontend/src/pages/Discover.tsx
git commit -m "feat: add location filter to discovery feed endpoint and Discover UI"
```
