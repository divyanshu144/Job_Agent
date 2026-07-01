# Semantic Stage-1 Discovery Matching Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace discovery's literal keyword Stage-1 with an embedding cosine-similarity gate (job vs. candidate intent), reusing the live `text-embedding-3-small` + pgvector infra, and add an admin endpoint to re-score the backlog of `filtered` jobs through it.

**Architecture:** Embed each job's `raw_text` and store the vector on the `Job` row. Build a candidate "intent" vector from `target_roles` + key skills + headline. `_process_job` (and the batch path) gate on `cosine(job, intent) >= threshold`, falling back to the existing keyword `_stage1_pass` when embeddings are unavailable. Location filter and Haiku Stage-2 are unchanged.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.0 async · Alembic · pgvector · OpenAI embeddings.

## Global Constraints

- Import `from backend.config import settings`; never read env elsewhere.
- Routes use `settings.api_prefix`; DI `Depends(get_db)`; background tasks own `SessionLocal()`.
- Reuse `backend/services/memory.py` helpers: `embed_texts`, `dense_cosine_similarity`, `_pgvector_available`, `_vector_literal`. Do NOT reimplement embedding/cosine.
- Embedding dimension is `settings.embedding_dimensions` (1536). Model is `settings.embedding_model` ("text-embedding-3-small").
- pgvector column work is Postgres-only and MUST be guarded exactly like `alembic/versions/0012_pgvector_embeddings.py` (SQLite test path must not execute `vector` DDL).
- `make check` (fmt + ruff + mypy + schema-drift + pytest cov>=70) green.
- Admin-only: discovery routes stay `require_admin`.

---

### Task 1: Job embedding columns + Alembic migration 0013

**Files:**
- Modify: `backend/models.py` (class `Job`)
- Create: `alembic/versions/0013_job_embeddings.py`
- Test: `tests/test_migrations.py` (append) — or `tests/test_services/test_discovery.py` for the model fields

**Interfaces:**
- Produces: `Job.embedding_json: str | None`, `Job.embedding_model: str | None` (ORM). The
  `embedding_vector` pgvector column is raw-SQL only (not an ORM attribute), mirroring `MemoryChunk`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_discovery.py`:

```python
def test_job_model_has_embedding_columns():
    from backend.models import Job

    j = Job(raw_text="x", dedup_hash="h", discovery_run_id="r")
    assert j.embedding_json is None
    assert j.embedding_model is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_discovery.py::test_job_model_has_embedding_columns -q`
Expected: FAIL — `Job` has no `embedding_json`.

- [ ] **Step 3: Add ORM columns**

In `backend/models.py`, class `Job`, after `matched_profiles`:

```python
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
```

- [ ] **Step 4: Create the migration**

Create `alembic/versions/0013_job_embeddings.py` (mirror 0012 for the `jobs` table):

```python
"""add job embeddings for semantic discovery

Revision ID: 0013_job_embeddings
Revises: 0012_pgvector_embeddings
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013_job_embeddings"
down_revision: Union[str, None] = "0012_pgvector_embeddings"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _has_vector_extension() -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("select exists(select 1 from pg_extension where extname = 'vector')"))
        .scalar()
    )


def _vector_available() -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("select exists(select 1 from pg_available_extensions where name = 'vector')"))
        .scalar()
    )


def upgrade() -> None:
    existing = _columns("jobs")
    if "embedding_model" not in existing:
        op.add_column("jobs", sa.Column("embedding_model", sa.String(), nullable=True))
    if "embedding_json" not in existing:
        op.add_column("jobs", sa.Column("embedding_json", sa.Text(), nullable=True))

    if _vector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if _has_vector_extension() and "embedding_vector" not in existing:
        op.execute("ALTER TABLE jobs ADD COLUMN embedding_vector vector(1536)")


def downgrade() -> None:
    existing = _columns("jobs")
    if _has_vector_extension() and "embedding_vector" in existing:
        op.execute("ALTER TABLE jobs DROP COLUMN embedding_vector")
    if "embedding_json" in existing:
        op.drop_column("jobs", "embedding_json")
    if "embedding_model" in existing:
        op.drop_column("jobs", "embedding_model")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_services/test_discovery.py::test_job_model_has_embedding_columns tests/test_migrations.py -q`
Expected: PASS (model field test + existing migration tests still green).

- [ ] **Step 6: Commit**

```bash
git add backend/models.py alembic/versions/0013_job_embeddings.py tests/test_services/test_discovery.py
git commit -m "feat(discovery): add job embedding columns + migration 0013"
```

---

### Task 2: Semantic primitives — intent text, gate, threshold config

**Files:**
- Modify: `backend/config.py` (add setting)
- Modify: `backend/services/discovery.py` (add functions + imports)
- Test: `tests/test_services/test_discovery.py`

**Interfaces:**
- Produces:
  - `settings.discovery_semantic_threshold: float` (default `0.30`, env `DISCOVERY_SEMANTIC_THRESHOLD`).
  - `build_intent_text(profile) -> str`
  - `semantic_stage1(job_embedding: list[float] | None, intent_embedding: list[float] | None, threshold: float) -> bool | None` (None => embeddings unavailable, caller falls back to keyword).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services/test_discovery.py`:

```python
def test_build_intent_text_combines_roles_skills_headline():
    from backend.services.discovery import build_intent_text

    p = Profile(
        yaml_data="identity:\n  headline: AI engineer building LLM systems\n",
        cv_text="",
        merged_profile="",
        profile_review_data=json.dumps(
            {"target_roles": ["AI Engineer"], "key_skills": ["Python", "RAG"]}
        ),
    )
    text = build_intent_text(p)
    assert "AI Engineer" in text and "Python" in text and "LLM systems" in text


def test_semantic_stage1_threshold_and_fallback_signal():
    from backend.services.discovery import semantic_stage1

    near = [1.0, 0.0, 0.0]
    same = [1.0, 0.0, 0.0]
    far = [0.0, 1.0, 0.0]
    assert semantic_stage1(same, near, 0.5) is True
    assert semantic_stage1(far, near, 0.5) is False
    assert semantic_stage1(None, near, 0.5) is None
    assert semantic_stage1(same, None, 0.5) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_discovery.py -k "intent_text or fallback_signal" -q`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Add the config setting**

In `backend/config.py`, class `Settings`, after `pgvector_enabled`:

```python
    discovery_semantic_threshold: float = 0.30
```

- [ ] **Step 4: Implement the primitives**

In `backend/services/discovery.py`, add near `search_profiles_for_profile` (and add
`import yaml` if not already imported at top — it is present):

```python
from backend.services.memory import dense_cosine_similarity, embed_texts


def build_intent_text(profile: Any) -> str:
    """Compact 'what the candidate wants + is' string for embedding: target roles +
    key skills + identity headline."""
    if profile is None:
        return ""
    review = parse_profile_review_data(profile.profile_review_data)
    parts: list[str] = list(review.target_roles) + list(review.key_skills)
    try:
        data = yaml.safe_load(profile.yaml_data) or {}
        headline = ((data.get("identity") or {}).get("headline") or "") if isinstance(data, dict) else ""
        if headline.strip():
            parts.append(headline.strip())
    except yaml.YAMLError:
        pass
    return ", ".join(p for p in parts if p and p.strip())


def semantic_stage1(
    job_embedding: list[float] | None,
    intent_embedding: list[float] | None,
    threshold: float,
) -> bool | None:
    """Semantic Stage-1 gate. Returns True/False by cosine threshold when both embeddings
    exist; None to signal 'embeddings unavailable' so the caller falls back to keyword."""
    if not job_embedding or not intent_embedding:
        return None
    return dense_cosine_similarity(job_embedding, intent_embedding) >= threshold
```

(Note: `embed_texts` is imported here for use in Task 3.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_services/test_discovery.py -k "intent_text or fallback_signal" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/services/discovery.py tests/test_services/test_discovery.py
git commit -m "feat(discovery): semantic intent text + cosine Stage-1 gate + threshold config"
```

---

### Task 3: Wire the semantic gate into `_process_job` + all fetch paths

**Files:**
- Modify: `backend/services/discovery.py` (`_process_job` ~143-183; `_run_discovery_task` ~254; `_run_source_task` ~410; `_run_batch_discovery_task` ~559 incl. the inline Stage-1 at ~654)
- Test: `tests/test_services/test_discovery.py`

**Interfaces:**
- Consumes: `semantic_stage1`, `build_intent_text`, `embed_texts` (Task 2); `_vector_literal`, `_pgvector_available` from `backend.services.memory`.
- Produces: `_process_job(..., job_embedding=None, intent_embedding=None)` new keyword params; a `_store_job_embedding(db, job_id, embedding)` helper.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services/test_discovery.py`:

```python
async def test_process_job_semantic_gate_filters_distant_job(session):
    from unittest.mock import patch
    from backend.services.discovery import SearchProfile, _process_job
    from backend.services.hn_client import RawJob

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(id="ps1", yaml_data="x", cv_text="", merged_profile="m",
                      last_refreshed_at=datetime.now(timezone.utc))
    session.add_all([run, profile]); await session.commit()
    raw = RawJob(source_id="s", source_url="u", raw_text="Backend Engineer role " * 5, dedup_hash="semantic-far")
    profiles = [SearchProfile(name="p", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65)]

    # job embedding far from intent -> filtered by semantic gate (no keyword fallback since embeddings present)
    with patch("backend.services.discovery.settings.discovery_semantic_threshold", 0.5):
        await _process_job(session, run.id, raw, profiles, profile, "compact",
                           job_embedding=[0.0, 1.0], intent_embedding=[1.0, 0.0])
    job = (await session.execute(select(Job).where(Job.dedup_hash == "semantic-far"))).scalar_one()
    assert job.state == "filtered"
    assert job.embedding_json is not None  # embedding still stored


async def test_process_job_falls_back_to_keyword_when_no_embeddings(session):
    from backend.services.discovery import SearchProfile, _process_job
    from backend.services.hn_client import RawJob

    run = DiscoveryRun(source="hn", status="running", started_at=datetime.now(timezone.utc))
    profile = Profile(id="ps2", yaml_data="x", cv_text="", merged_profile="m",
                      last_refreshed_at=datetime.now(timezone.utc))
    session.add_all([run, profile]); await session.commit()
    # keyword does NOT match -> filtered (proves fallback path runs)
    raw = RawJob(source_id="s", source_url="u", raw_text="Sales manager wanted " * 5, dedup_hash="kw-fallback")
    profiles = [SearchProfile(name="p", target_roles=["Backend Engineer"], allowed_locations=[], min_score=65)]

    await _process_job(session, run.id, raw, profiles, profile, "compact",
                       job_embedding=None, intent_embedding=None)
    job = (await session.execute(select(Job).where(Job.dedup_hash == "kw-fallback"))).scalar_one()
    assert job.state == "filtered"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_services/test_discovery.py -k "semantic_gate_filters or falls_back_to_keyword" -q`
Expected: FAIL — `_process_job` has no `job_embedding`/`intent_embedding` params.

- [ ] **Step 3: Add the embedding-store helper + update `_process_job`**

In `backend/services/discovery.py` add imports at top: `from sqlalchemy import text` (present already for other modules? add if missing) and `from backend.services.memory import _pgvector_available, _vector_literal`.

Add helper:

```python
async def _store_job_embedding(db: AsyncSession, job_id: str, embedding: list[float]) -> None:
    await db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(embedding_json=json.dumps(embedding), embedding_model=settings.embedding_model)
    )
    await db.commit()
    if await _pgvector_available(db):
        await db.execute(
            text("UPDATE jobs SET embedding_vector = CAST(:v AS vector) WHERE id = :id"),
            {"id": job_id, "v": _vector_literal(embedding)},
        )
        await db.commit()
```

Change `_process_job` signature to add keyword params:
```python
async def _process_job(
    db: AsyncSession,
    run_id: str,
    raw: RawJob,
    profiles: list[SearchProfile],
    profile: Any,
    compact: str,
    source_tag: str = "hn",
    job_embedding: list[float] | None = None,
    intent_embedding: list[float] | None = None,
) -> None:
```

After the Job is created + committed (currently line ~178, right before the `_stage1_pass` check), insert:
```python
    if job_embedding:
        await _store_job_embedding(db, job.id, job_embedding)
```

Replace the keyword Stage-1 check (currently `if not _stage1_pass(raw.raw_text, profiles):`) with:
```python
    passed = semantic_stage1(job_embedding, intent_embedding, settings.discovery_semantic_threshold)
    if passed is None:
        passed = _stage1_pass(raw.raw_text, profiles)
    if not passed:
        await db.execute(update(Job).where(Job.id == job.id).values(state="filtered"))
        await db.commit()
        return
```

- [ ] **Step 4: Compute embeddings in the fetch tasks and pass them in**

In `_run_discovery_task` and `_run_source_task`, after `profiles`/`compact` are built and `raw_jobs` fetched, add:
```python
            intent_emb_list = await embed_texts([build_intent_text(profile)])
            intent_emb = intent_emb_list[0] if intent_emb_list else None
            job_emb_list = await embed_texts([r.raw_text[:2000] for r in raw_jobs]) if raw_jobs else None
            job_embs = {r.dedup_hash: (job_emb_list[i] if job_emb_list else None) for i, r in enumerate(raw_jobs)}
```
and change the `_process_job(...)` call inside the bounded worker to:
```python
                await _process_job(
                    db, run_id, raw, profiles, profile, compact, source_tag=source,
                    job_embedding=job_embs.get(raw.dedup_hash), intent_embedding=intent_emb,
                )
```
(In `_run_source_task` the tag is `source`; keep the existing `source_tag=` value.)

In `_run_batch_discovery_task`, at the inline pre-filter (currently
`state = "discovered" if _stage1_pass(raw.raw_text, profiles) else "filtered"`), compute the
same `intent_emb` + per-job `job_embs` above the loop, then replace that line with:
```python
                passed = semantic_stage1(job_embs.get(raw.dedup_hash), intent_emb, settings.discovery_semantic_threshold)
                if passed is None:
                    passed = _stage1_pass(raw.raw_text, profiles)
                state = "discovered" if passed else "filtered"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_services/test_discovery.py -q`
Expected: PASS (new + existing). Then `ruff check backend/services/discovery.py && mypy backend/services/discovery.py` clean.

- [ ] **Step 6: Commit**

```bash
git add backend/services/discovery.py tests/test_services/test_discovery.py
git commit -m "feat(discovery): semantic Stage-1 gate in process_job + all fetch paths (keyword fallback)"
```

---

### Task 4: Backlog re-score endpoint `POST /api/discovery/rescore`

**Files:**
- Modify: `backend/services/discovery.py` (add `rescore_filtered_jobs` service + `run_rescore`)
- Modify: `backend/routes/discovery.py` (add endpoint)
- Test: `tests/test_routes/test_discovery.py`

**Interfaces:**
- Consumes: `_require_search_criteria` (Phase 1), `search_profiles_for_profile`, `build_intent_text`, `embed_texts`, `semantic_stage1`, the `_process_job` internals.
- Produces: `POST /api/discovery/rescore` -> `{"rescored": int}` (fires a background task).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routes/test_discovery.py`:

```python
async def test_rescore_requires_admin_and_criteria(app_client, db_session):
    from datetime import datetime, timezone
    from backend.models import Profile

    db_session.add(Profile(yaml_data="identity:\n  name: A\n", cv_text="", merged_profile="",
                           last_refreshed_at=datetime.now(timezone.utc), user_id="test-user-id"))
    await db_session.commit()
    resp = await app_client.post("/api/discovery/rescore")
    assert resp.status_code == 422  # no criteria


async def test_rescore_starts_when_criteria_present(app_client, db_session):
    import json
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch
    from backend.models import Profile

    db_session.add(Profile(
        yaml_data="identity:\n  name: A\n", cv_text="", merged_profile="",
        profile_review_data=json.dumps({"target_roles": ["AI Engineer"], "work_preferences": {"locations": ["Remote"]}}),
        last_refreshed_at=datetime.now(timezone.utc), user_id="test-user-id"))
    await db_session.commit()
    with patch("backend.routes.discovery.run_rescore", new_callable=AsyncMock, return_value="rescore-1"):
        resp = await app_client.post("/api/discovery/rescore")
    assert resp.status_code == 200
    assert "run_id" in resp.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_routes/test_discovery.py -k rescore -q`
Expected: FAIL — endpoint not defined (404).

- [ ] **Step 3: Implement the service**

In `backend/services/discovery.py` add:

```python
async def _run_rescore_task(run_id: str, user_id: str) -> None:
    async with SessionLocal() as db:
        profile = await get_or_build_profile(db, user_id=user_id)
        profiles = search_profiles_for_profile(profile)
        compact = build_compact_profile(profile.yaml_data, profile.cv_text)
        intent_list = await embed_texts([build_intent_text(profile)])
        intent_emb = intent_list[0] if intent_list else None
        filtered = (
            (await db.execute(select(Job).where(Job.state == "filtered").limit(500)))
            .scalars()
            .all()
        )
    # Re-run each through the pipeline via a fresh RawJob-like path: reset state and reuse _process_job
    sem = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _one(job_id: str, raw_text: str, dedup_hash: str, source_id: str, source_url: str) -> None:
        async with sem, SessionLocal() as db:
            # delete the stale filtered row so _process_job re-creates + re-scores it
            await db.execute(update(Job).where(Job.id == job_id).values(dedup_hash=dedup_hash + "::rescore-old"))
            await db.commit()
            from backend.services.hn_client import RawJob
            raw = RawJob(source_id=source_id, source_url=source_url, raw_text=raw_text, dedup_hash=dedup_hash)
            emb_list = await embed_texts([raw_text[:2000]])
            await _process_job(db, run_id, raw, profiles, profile, compact, source_tag="rescore",
                               job_embedding=(emb_list[0] if emb_list else None), intent_embedding=intent_emb)

    await asyncio.gather(*[
        _one(j.id, j.raw_text, j.dedup_hash, j.source_id, j.source_url) for j in filtered
    ], return_exceptions=True)
    async with SessionLocal() as db:
        await db.execute(update(DiscoveryRun).where(DiscoveryRun.id == run_id).values(
            status="complete", completed_at=datetime.now(timezone.utc)))
        await db.commit()


async def run_rescore(db: AsyncSession, user_id: str) -> str:
    run = DiscoveryRun(source="rescore", triggered_by="manual", status="running",
                       started_at=datetime.now(timezone.utc))
    db.add(run); await db.commit()
    task = asyncio.create_task(_run_rescore_task(run.id, user_id))
    _background_tasks.add(task); task.add_done_callback(_background_tasks.discard)
    return run.id
```

(Note: renaming the old row's `dedup_hash` frees the unique hash so `_process_job` re-creates and
re-scores the job. The stale `::rescore-old` row remains `filtered` and is ignored by the feed.)

- [ ] **Step 4: Implement the endpoint**

In `backend/routes/discovery.py`, import `run_rescore`, and add:

```python
@router.post("/discovery/rescore")
async def trigger_rescore(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Re-evaluate the backlog of filtered jobs against current criteria (semantic gate)."""
    await _require_search_criteria(db, current_user.id)
    run_id = await run_rescore(db, current_user.id)
    return {"run_id": run_id}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_routes/test_discovery.py -k rescore -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/discovery.py backend/routes/discovery.py tests/test_routes/test_discovery.py
git commit -m "feat(discovery): POST /discovery/rescore to re-evaluate the filtered backlog"
```

---

### Task 5: Full verification + release prep

**Files:**
- Modify: `HANDOFF.md`, `tasks/todo.md`

- [ ] **Step 1: Run the full check**

Run: `make check`
Expected: PASS (fmt + ruff + mypy + schema-drift + pytest cov>=70, all green).

- [ ] **Step 2: Update handoff + todo**

Mark Phase 2 items done in `tasks/todo.md`; in `HANDOFF.md` set Next action:
"run `aws-migrate.yml` (migration 0013), tag `v1.3.0`, then `POST /api/discovery/rescore` and
calibrate `DISCOVERY_SEMANTIC_THRESHOLD`."

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md tasks/todo.md
git commit -m "docs: discovery semantic matching (Phase 2) complete"
```

---

## Self-Review

**Spec coverage:**
- Job embedding columns + migration → Task 1. ✅
- Intent vector + semantic gate + threshold config → Task 2. ✅
- Semantic gate replaces keyword in `_process_job` + all fetch/batch paths, with keyword fallback + embedding storage → Task 3. ✅
- Backlog re-score endpoint → Task 4. ✅
- make check + migration/rollout note → Task 5. ✅
- Reuse of `memory.py` helpers, pgvector guarded like 0012, admin-only → constraints honored. ✅

**Type consistency:** `semantic_stage1(job_embedding, intent_embedding, threshold) -> bool | None` and `build_intent_text(profile) -> str` defined in Task 2, used identically in Tasks 3-4. `_process_job(..., job_embedding=None, intent_embedding=None)` defined in Task 3, called with those kwargs in Tasks 3-4. `run_rescore(db, user_id)` defined Task 4, called from the route with those args. `_store_job_embedding(db, job_id, embedding)` defined + used in Task 3.

**Placeholders:** none — every code step contains complete code. The rescore dedup-hash rename is explained inline.

**Risk note for the reviewer/implementer:** Task 4's rescore mutates the old row's `dedup_hash` to free it, then re-creates via `_process_job`. Confirm the feed query filters on `state='scored'` (it does) so the orphaned `::rescore-old` filtered rows never surface. An alternative (re-score in place without delete) is possible but larger; this approach reuses `_process_job` wholesale.
