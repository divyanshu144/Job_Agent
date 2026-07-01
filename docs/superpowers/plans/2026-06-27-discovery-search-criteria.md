# Admin Discovery Search-Criteria Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make admin-triggered discovery score jobs against search criteria stored on the admin's DB profile (target roles + locations) instead of an on-disk file that isn't deployed, and gate the Discover page with a "set up your search" panel instead of silently returning 0.

**Architecture:** Add a `target_roles` list to the per-user `ProfileReviewData` (JSON column, no migration). A new `search_profiles_for_profile(profile)` builds the discovery `SearchProfile` list from that profile. All three discovery run entrypoints take a `user_id`, load that user's profile, and build criteria from it — replacing every `_load_search_profiles()` (file) call. Discovery routes (already `require_admin`) reject with 422 when criteria are missing. The Discover page renders a setup panel when criteria are absent.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · React 19 + TS · Vite.

## Global Constraints

- Import settings via `from backend.config import settings`; never read `os.environ` elsewhere.
- Routes use `settings.api_prefix`; never hardcode `/api`.
- DB sessions via `Depends(get_db)` in routes; background tasks own their own `SessionLocal()`.
- `make check` (fmt + lint + mypy + `scripts/check_schema_drift.py` + pytest, cov ≥ 70%) must pass.
- Any change to a backend Pydantic schema that has a TS mirror must update `frontend/src/types/index.ts` in the same task (schema-drift check enforces this).
- Generated/user copy: no em/en dashes; plain human language.
- Admin-only: discovery routes already use `Depends(require_admin)`; do not change that.

---

### Task 1: Add `target_roles` to `ProfileReviewData` (+ TS mirror)

**Files:**
- Modify: `backend/schemas.py` (class `ProfileReviewData`)
- Modify: `frontend/src/types/index.ts` (interface `ProfileReviewData`)
- Test: `tests/test_services/test_profile_builder.py`

**Interfaces:**
- Produces: `ProfileReviewData.target_roles: list[str]` (default `[]`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_profile_builder.py`:

```python
def test_profile_review_data_round_trips_target_roles():
    from backend.services.profile_builder import (
        parse_profile_review_data,
        serialize_profile_review_data,
    )

    data = ProfileReviewData(target_roles=["AI Engineer", "Backend Engineer"])
    raw = serialize_profile_review_data(data)

    assert parse_profile_review_data(raw).target_roles == ["AI Engineer", "Backend Engineer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_profile_builder.py::test_profile_review_data_round_trips_target_roles -q`
Expected: FAIL — `ProfileReviewData` has no `target_roles` (TypeError / attribute).

- [ ] **Step 3: Add the field (backend)**

In `backend/schemas.py`, class `ProfileReviewData`, add the field (next to `key_skills`):

```python
    target_roles: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Mirror in TS**

In `frontend/src/types/index.ts`, interface `ProfileReviewData`, add:

```typescript
  target_roles: string[];
```

Also add `target_roles: []` to the `emptyReviewData()` factory in `frontend/src/pages/ProfileSetup.tsx` so existing form state stays valid.

- [ ] **Step 5: Run test + schema drift**

Run: `python -m pytest tests/test_services/test_profile_builder.py::test_profile_review_data_round_trips_target_roles -q && python scripts/check_schema_drift.py`
Expected: PASS, and "Schema drift check passed".

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py frontend/src/types/index.ts frontend/src/pages/ProfileSetup.tsx tests/test_services/test_profile_builder.py
git commit -m "feat(profile): add target_roles to ProfileReviewData"
```

---

### Task 2: `search_profiles_for_profile()` builder

**Files:**
- Modify: `backend/services/discovery.py` (add constant + function near `_load_search_profiles`)
- Test: `tests/test_services/test_discovery.py` (create if absent)

**Interfaces:**
- Consumes: `ProfileReviewData.target_roles` (Task 1); existing `SearchProfile` dataclass; `parse_profile_review_data` from `backend.services.profile_builder`.
- Produces: `search_profiles_for_profile(profile: Profile) -> list[SearchProfile]` and `DISCOVERY_DEFAULT_MIN_SCORE: int = 60`. Returns `[]` when target_roles or locations are empty.

- [ ] **Step 1: Write the failing test**

Create/append `tests/test_services/test_discovery.py`:

```python
import json

from backend.models import Profile


def _profile(target_roles, locations):
    return Profile(
        yaml_data="identity:\n  name: Admin\n",
        cv_text="",
        merged_profile="",
        profile_review_data=json.dumps(
            {"target_roles": target_roles, "work_preferences": {"locations": locations}}
        ),
    )


def test_search_profiles_for_profile_builds_from_roles_and_locations():
    from backend.services.discovery import DISCOVERY_DEFAULT_MIN_SCORE, search_profiles_for_profile

    profs = search_profiles_for_profile(_profile(["AI Engineer"], ["London", "Remote"]))

    assert len(profs) == 1
    assert profs[0].target_roles == ["AI Engineer"]
    assert profs[0].allowed_locations == ["London", "Remote"]
    assert profs[0].min_score == DISCOVERY_DEFAULT_MIN_SCORE


def test_search_profiles_for_profile_empty_when_roles_or_locations_missing():
    from backend.services.discovery import search_profiles_for_profile

    assert search_profiles_for_profile(_profile([], ["London"])) == []
    assert search_profiles_for_profile(_profile(["AI Engineer"], [])) == []
    assert search_profiles_for_profile(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_discovery.py -q`
Expected: FAIL — `cannot import name 'search_profiles_for_profile'`.

- [ ] **Step 3: Implement the builder**

In `backend/services/discovery.py`, add near `_load_search_profiles` (and add the import `from backend.services.profile_builder import parse_profile_review_data` to the existing profile_builder import line):

```python
DISCOVERY_DEFAULT_MIN_SCORE = 60


def search_profiles_for_profile(profile: Any) -> list[SearchProfile]:
    """Build discovery criteria from a user's saved Profile Review (target roles +
    locations). Returns [] when either required field is empty — callers treat that
    as 'search not configured'."""
    if profile is None:
        return []
    review = parse_profile_review_data(profile.profile_review_data)
    roles = [r.strip() for r in review.target_roles if r.strip()]
    locations = [loc.strip() for loc in review.work_preferences.locations if loc.strip()]
    if not roles or not locations:
        return []
    return [
        SearchProfile(
            name="my-search",
            target_roles=roles,
            allowed_locations=locations,
            min_score=DISCOVERY_DEFAULT_MIN_SCORE,
        )
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services/test_discovery.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/discovery.py tests/test_services/test_discovery.py
git commit -m "feat(discovery): build search criteria from the user's profile"
```

---

### Task 3: Thread `user_id` through all three run entrypoints; drop the file reader

**Files:**
- Modify: `backend/services/discovery.py` (entrypoints + background tasks at lines ~254-267, ~410-419, ~491-543, ~559-581)
- Test: `tests/test_services/test_discovery.py`

**Interfaces:**
- Consumes: `search_profiles_for_profile` (Task 2); `get_or_build_profile(db, user_id=...)`.
- Produces: `run_discovery(source, db, user_id)`, `run_all_discovery(db, user_id)`, `run_batch_discovery(source, db, user_id)` — all now take `user_id: str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_discovery.py`:

```python
import inspect


def test_run_entrypoints_accept_user_id():
    from backend.services import discovery

    for name in ("run_discovery", "run_all_discovery", "run_batch_discovery"):
        params = inspect.signature(getattr(discovery, name)).parameters
        assert "user_id" in params, f"{name} must take user_id"


def test_discovery_does_not_read_profile_yaml_file(monkeypatch):
    """The on-disk search-profiles file path must no longer be referenced by the run
    path — criteria come from the DB profile."""
    import backend.services.discovery as d

    src = inspect.getsource(d._run_discovery_task) + inspect.getsource(d._run_source_task) \
        + inspect.getsource(d._run_batch_discovery_task)
    assert "_load_search_profiles(" not in src
    assert "search_profiles_for_profile(" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_discovery.py -k "user_id or yaml_file" -q`
Expected: FAIL — entrypoints lack `user_id`; `_load_search_profiles(` still present.

- [ ] **Step 3: Implement — entrypoint signatures**

In `backend/services/discovery.py` change the three public entrypoints to take `user_id` and pass it to their background task:

`run_discovery` (~line 335):
```python
async def run_discovery(source: str, db: AsyncSession, user_id: str) -> str:
    """Public entry point. Creates DiscoveryRun, fires background task, returns run_id."""
    run = DiscoveryRun(
        source=source,
        triggered_by="manual",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    task = asyncio.create_task(_run_discovery_task(run.id, source, user_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return run.id
```

`run_all_discovery` (~line 517): add `user_id: str` param and pass it into `_run_all_discovery_task(run.id, sources, user_id)`.
`run_batch_discovery` (~line 543): add `user_id: str` param and pass it into `_run_batch_discovery_task(run.id, source, user_id)`.

- [ ] **Step 4: Implement — background task signatures + criteria source**

Update the three background tasks to take `user_id` and replace the file read with the profile-derived builder.

`_run_discovery_task` (~line 254): change signature to `async def _run_discovery_task(run_id: str, source: str, user_id: str) -> None:` and replace lines 266-267:
```python
            profile = await get_or_build_profile(db, user_id=user_id)
            profiles = search_profiles_for_profile(profile)
```

`_run_source_task` (~line 410): change signature to `async def _run_source_task(run_id: str, source: str, user_id: str) -> None:` and replace lines 418-419 with the same two lines above.

`_run_all_discovery_task` (~line 491): change signature to `async def _run_all_discovery_task(run_id: str, sources: list[str], user_id: str) -> None:` and pass `user_id` into every `_run_source_task(run_id, src, user_id)` call inside it.

`_run_batch_discovery_task` (~line 559): change signature to `async def _run_batch_discovery_task(run_id: str, source: str, user_id: str) -> None:` and replace lines 580-581 with the same two lines above.

Then delete the now-unused `_load_search_profiles` function (and its `Path`/`yaml` imports if they become unused — run `make lint` to confirm).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_services/test_discovery.py -q`
Expected: PASS (all, including the two new tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/discovery.py tests/test_services/test_discovery.py
git commit -m "feat(discovery): score against the triggering admin's profile criteria"
```

---

### Task 4: Route gate + pass `user_id` (4xx when criteria missing)

**Files:**
- Modify: `backend/routes/discovery.py` (4 handlers ~lines 88-132; add a helper + imports)
- Test: `tests/test_routes/test_discovery.py` (create if absent)

**Interfaces:**
- Consumes: `search_profiles_for_profile` (Task 2); `get_owned_profile` from `backend.services.profile_builder`; the `user_id`-taking entrypoints (Task 3).

- [ ] **Step 1: Write the failing test**

Create/append `tests/test_routes/test_discovery.py` (admin user is the default authed user in `app_client`):

```python
async def test_discovery_run_requires_search_criteria(app_client, db_session):
    from datetime import datetime, timezone
    from backend.models import Profile

    # admin profile with NO target_roles/locations
    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Admin\n",
            cv_text="",
            merged_profile="",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    resp = await app_client.post("/api/discovery/run?source=hn")

    assert resp.status_code == 422
    assert "target roles" in resp.json()["detail"].lower()


async def test_discovery_run_starts_when_criteria_present(app_client, db_session):
    import json
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch
    from backend.models import Profile

    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Admin\n",
            cv_text="",
            merged_profile="",
            profile_review_data=json.dumps(
                {"target_roles": ["AI Engineer"], "work_preferences": {"locations": ["Remote"]}}
            ),
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    with patch(
        "backend.routes.discovery.run_discovery", new_callable=AsyncMock, return_value="run-123"
    ) as run:
        resp = await app_client.post("/api/discovery/run?source=hn")

    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run-123"
    assert run.await_args.kwargs.get("user_id") == "test-user-id" or "test-user-id" in run.await_args.args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_routes/test_discovery.py -q`
Expected: FAIL — currently returns 200 (no gate) / `run_discovery` called without `user_id`.

- [ ] **Step 3: Implement the gate helper + apply to handlers**

In `backend/routes/discovery.py` add imports:
```python
from fastapi import HTTPException
from backend.services.profile_builder import get_owned_profile
from backend.services.discovery import search_profiles_for_profile
```
Add a helper:
```python
async def _require_search_criteria(db: AsyncSession, user_id: str) -> None:
    profile = await get_owned_profile(db, user_id)
    if not search_profiles_for_profile(profile):
        raise HTTPException(
            status_code=422,
            detail="Set up your search first — add target roles and locations.",
        )
```
In each of the 4 handlers (`trigger_discovery`, `trigger_all_discovery`, `trigger_batch_discovery`, `trigger_batch_all_discovery`), before launching, call `await _require_search_criteria(db, current_user.id)` and pass `user_id=current_user.id` to the run function. Example for `trigger_discovery`:
```python
    _validate_discovery_source(source)
    await _require_search_criteria(db, current_user.id)
    run_id = await run_discovery(source, db, user_id=current_user.id)
    return {"run_id": run_id}
```
Apply the analogous two changes to the other three handlers (`run_all_discovery(db, user_id=current_user.id)`, `run_batch_discovery(source, db, user_id=current_user.id)`, `run_batch_discovery("all", db, user_id=current_user.id)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_routes/test_discovery.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/discovery.py tests/test_routes/test_discovery.py
git commit -m "feat(discovery): gate runs on configured search criteria (422 when missing)"
```

---

### Task 5: Discover page — "Set up your search" panel + gate

**Files:**
- Modify: `frontend/src/pages/Discover.tsx`
- Modify: `frontend/src/api/client.ts` (only if a profile-review fetch/save wrapper is missing; reuse `getProfileReview`/`saveProfileReview` if present)

**Interfaces:**
- Consumes: `ProfileReviewData.target_roles` (Task 1); existing `api.getProfileReview()` / `api.saveProfileReview()`; the 422 from `POST /api/discovery/run*` (Task 4).

- [ ] **Step 1: Read the current page + API client**

Run: `sed -n '1,80p' frontend/src/pages/Discover.tsx` and `grep -n "getProfileReview\|saveProfileReview\|discoveryRun\|runDiscovery" frontend/src/api/client.ts`
Purpose: confirm the existing fetch/trigger wrappers and the empty-state block to replace.

- [ ] **Step 2: Add the setup panel + gate (manual verification feature)**

In `Discover.tsx`:
- On mount, load the review via `api.getProfileReview()`; derive `hasCriteria = review.target_roles.length > 0 && review.work_preferences.locations.length > 0`.
- When `!hasCriteria`, render a **"Set up your search"** panel (reuse the chip-input pattern from `ProfileSetup.tsx`): a target-roles chip input (≥1 required) and a locations chip input with a "Remote" chip (≥1 required), and a **Save** button that calls `api.saveProfileReview({ ...review, target_roles, work_preferences: { ...wp, locations } })`. Disable the Fetch/Batch buttons while `!hasCriteria`.
- Replace the current "No matched jobs found. Adjust search_profiles in data/candidate_profile.yaml" empty state with this panel / a "Set up your search to start" prompt.
- If a Fetch/Batch call returns 422, surface the returned `detail` and show the setup panel.

(UI step — no unit test; verified at Step 3.)

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Discover.tsx frontend/src/api/client.ts
git commit -m "feat(discover): set-up-your-search panel + gate when criteria missing"
```

---

### Task 6: Full verification + release prep

**Files:**
- Modify: `HANDOFF.md`, `tasks/todo.md`

- [ ] **Step 1: Run the full check**

Run: `make check`
Expected: PASS — fmt clean, lint (ruff + mypy + schema drift) clean, all tests pass, coverage ≥ 70%.

- [ ] **Step 2: Manual smoke (local, optional but recommended)**

Render the Discover flow per `verify` skill if a local stack is available: with no criteria → setup panel shows and Fetch is disabled; after saving roles+locations → Fetch enabled and a run starts (returns a run_id). If no local stack, note it as deferred to staging.

- [ ] **Step 3: Update handoff + todo**

Mark the Phase 1 checklist items done in `tasks/todo.md`; update `HANDOFF.md` with the new state and "Next action: tag v1.2.0 to deploy".

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md tasks/todo.md
git commit -m "docs: discovery search-criteria Phase 1 complete"
```

---

## Self-Review

**Spec coverage:**
- `target_roles` field → Task 1. ✅
- Builder from DB profile → Task 2. ✅
- Discovery reads criteria from admin profile, drops file dependency, per-user_id → Task 3. ✅
- 4xx gate when missing → Task 4. ✅
- Discover-page setup panel + empty-state replacement → Task 5. ✅
- No DB migration → confirmed (JSON field). ✅
- make check / typecheck / build → Task 6 + per-task. ✅
- Deferred multi-user/semantic items → not in plan (correct; tracked in spec). ✅

**Type consistency:** `search_profiles_for_profile(profile) -> list[SearchProfile]` and `DISCOVERY_DEFAULT_MIN_SCORE` defined in Task 2 and used identically in Tasks 3-4; entrypoint signatures `run_discovery(source, db, user_id)` / `run_all_discovery(db, user_id)` / `run_batch_discovery(source, db, user_id)` defined in Task 3 and called with those exact kwargs in Task 4. `ProfileReviewData.target_roles: list[str]` (Task 1) used in Tasks 2 and 5. Consistent.

**Placeholders:** none — every code step shows the code; the one UI task (Task 5) is explicitly a manual-verification feature with a read step to ground it.
