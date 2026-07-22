# Resume Editor — Plan 1: Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the editable, versioned `ResumeDocument` data layer — tables, schemas, deterministic master seed from the profile, version CRUD, `rev`-based optimistic-concurrency writes, undo/redo history, and the `always`/`never` rules store — with no LLM involvement.

**Architecture:** New SQLAlchemy models + one Alembic migration; a thin `resume_document` service that owns the compare-and-swap write path, the one-active-version invariant, and the bounded revision snapshot buffer; a new `routes/resume.py` router following the existing `targets.py` pattern (per-user ownership, `get_current_user` + `get_db` dependencies). This plan is the base that Plans 2–6 (chat agent, faithfulness, master-as-base tailoring, frontend, cover-letter) build on. It ships working, testable software on its own: you can create/seed/edit/version/undo a resume via the API.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · PostgreSQL (asyncpg) · Alembic · pytest (async, `Base.metadata.create_all` per-session schema).

## Global Constraints

- Import settings via `from backend.config import settings`; never read `os.environ` outside `config.py`.
- DB session is always injected: `db: AsyncSession = Depends(get_db)`. Never construct `AsyncSession` manually.
- Route paths never hardcode `/api`; the router is registered in `main.py` with `prefix=settings.api_prefix`. Path strings inside the router are relative (e.g. `/resume`), matching `targets.py`.
- Services are plain async functions/thin classes, no global state. Routes call services.
- `make check` (`fmt` + `lint` + `test`) must pass. `make fmt` = ruff format; lint = ruff check + mypy.
- Every new route has an integration test in `tests/test_routes/` covering happy path **and** the auth requirement.
- Generated resume content is the `ResumeTailorerOutput` shape (already in `backend/schemas.py`): `headline, summary, skills[], experience[ResumeExperienceItem], projects[ResumeProjectItem], education[ResumeEducationItem], tailored_bullets[], omitted_items[]`.
- Model IDs for later plans: resume path = `claude-opus-4-8`, fallback = `claude-sonnet-4-6`. (Not used in Plan 1, but the config settings are added here so later plans consume them.)

---

### Task 1: ORM models + Alembic migration

**Files:**
- Modify: `backend/models.py` (append new models near the other per-user tables)
- Create: `alembic/versions/0014_resume_documents.py`
- Test: `tests/test_models/test_resume_documents_model.py`

**Interfaces:**
- Produces: ORM classes `ResumeDocument`, `CoverLetterDocument`, `ResumeDocumentRevision`, `ResumeEditRule` with the columns below. `ResumeDocument`/`CoverLetterDocument` fields: `id, user_id, analysis_id, kind, name, content_json, is_active, rev, created_at, updated_at`. `ResumeDocumentRevision` fields: `id, document_id, doc_kind, rev, content_json, source, summary, created_at`. `ResumeEditRule` fields: `id, user_id, mode, text, scope, created_at`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models/test_resume_documents_model.py
from __future__ import annotations

import backend.models  # noqa: F401
from backend.models import ResumeDocument, ResumeDocumentRevision, ResumeEditRule
from tests.factories import make_user


async def test_resume_document_defaults(db_session):
    user = await make_user(db_session)
    doc = ResumeDocument(
        user_id=user.id, kind="master", name="Default", content_json="{}"
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    assert doc.id
    assert doc.rev == 0
    assert doc.is_active is False
    assert doc.analysis_id is None


async def test_revision_and_rule_persist(db_session):
    user = await make_user(db_session)
    doc = ResumeDocument(user_id=user.id, kind="master", name="Default", content_json="{}")
    db_session.add(doc)
    await db_session.flush()
    db_session.add(
        ResumeDocumentRevision(
            document_id=doc.id, doc_kind="resume", rev=0, content_json="{}", source="seed"
        )
    )
    db_session.add(ResumeEditRule(user_id=user.id, mode="never", text="utilized", scope="resume"))
    await db_session.commit()
    assert doc.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models/test_resume_documents_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ResumeDocument'`.

- [ ] **Step 3: Add the models**

Append to `backend/models.py` (the file already imports `Boolean, DateTime, ForeignKey, Index, Integer, String, Text` and defines `_utcnow`):

```python
class ResumeDocument(Base):
    __tablename__ = "resume_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None, index=True
    )
    kind: Mapped[str] = mapped_column(String)  # "master" | "analysis"
    name: Mapped[str] = mapped_column(String, default="Default")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optimistic-concurrency counter (see design §5.3). Bumped on every accepted write.
    rev: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class CoverLetterDocument(Base):
    __tablename__ = "cover_letter_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None, index=True
    )
    kind: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, default="Default")
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    rev: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ResumeDocumentRevision(Base):
    __tablename__ = "resume_document_revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(String, index=True)
    doc_kind: Mapped[str] = mapped_column(String)  # "resume" | "cover_letter"
    rev: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String)  # seed|tailor|inline|chat|undo
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResumeEditRule(Base):
    __tablename__ = "resume_edit_rules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String)  # "always" | "never"
    text: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String, default="resume")  # resume|cover_letter|both
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Run the model test to verify it passes**

Run: `pytest tests/test_models/test_resume_documents_model.py -v`
Expected: PASS (tests create tables via `Base.metadata.create_all`).

- [ ] **Step 5: Write the Alembic migration**

Find the current head: `grep -rl "down_revision" alembic/versions | xargs grep -L "down_revision = None" >/dev/null; python -c "import glob;print(sorted(glob.glob('alembic/versions/0*.py'))[-1])"` → the highest is `0013_job_embeddings.py`. Open it and copy its `revision` value to use as this migration's `down_revision`.

```python
# alembic/versions/0014_resume_documents.py
"""resume editor: documents, versions, revisions, edit rules"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_resume_documents"
down_revision = "0013_job_embeddings"  # confirm against 0013's `revision =` value
branch_labels = None
depends_on = None


def _doc_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), index=True),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default="Default"),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rev", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(f"ix_{name}_analysis_id", name, ["analysis_id"])


def upgrade() -> None:
    _doc_table("resume_documents")
    _doc_table("cover_letter_documents")
    op.create_table(
        "resume_document_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), nullable=False, index=True),
        sa.Column("doc_kind", sa.String(), nullable=False),
        sa.Column("rev", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "resume_edit_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), index=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False, server_default="resume"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resume_edit_rules")
    op.drop_table("resume_document_revisions")
    op.drop_table("cover_letter_documents")
    op.drop_table("resume_documents")
```

- [ ] **Step 6: Verify the migration applies**

Run: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: no errors; the four tables create and drop cleanly.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py alembic/versions/0014_resume_documents.py tests/test_models/test_resume_documents_model.py
git commit -m "feat(resume-editor): resume document models + migration"
```

---

### Task 2: Pydantic schemas

**Files:**
- Modify: `backend/schemas.py` (append)
- Test: `tests/test_schemas/test_resume_document_schemas.py`

**Interfaces:**
- Produces: `ResumeDocumentResponse` (fields: `id, kind, name, is_active, rev, content: ResumeTailorerOutput, updated_at`), `ResumeVersionSummary` (`id, name, is_active, rev, updated_at`), `ResumeContentUpdate` (`base_rev: int, content: ResumeTailorerOutput`), `ResumeVersionCreate` (`name: str, clone_active: bool = True`), `ResumeVersionPatch` (`name: str | None = None, make_active: bool | None = None`), `EditRuleCreate` (`mode, text, scope`), `EditRuleResponse` (`id, mode, text, scope`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas/test_resume_document_schemas.py
from backend.schemas import ResumeContentUpdate, ResumeDocumentResponse, ResumeTailorerOutput


def test_content_update_requires_base_rev():
    upd = ResumeContentUpdate(base_rev=3, content=ResumeTailorerOutput(headline="Eng"))
    assert upd.base_rev == 3
    assert upd.content.headline == "Eng"


def test_document_response_carries_rev_and_content():
    resp = ResumeDocumentResponse(
        id="d1", kind="master", name="Default", is_active=True, rev=2,
        content=ResumeTailorerOutput(headline="Eng"), updated_at="2026-07-22T00:00:00Z",
    )
    assert resp.rev == 2 and resp.content.headline == "Eng"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas/test_resume_document_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'ResumeContentUpdate'`.

- [ ] **Step 3: Add the schemas**

Append to `backend/schemas.py` (it already defines `ResumeTailorerOutput` and imports `BaseModel`, `Field`):

```python
class ResumeVersionSummary(BaseModel):
    id: str
    name: str
    is_active: bool
    rev: int
    updated_at: datetime


class ResumeDocumentResponse(BaseModel):
    id: str
    kind: str
    name: str
    is_active: bool
    rev: int
    content: ResumeTailorerOutput
    updated_at: datetime


class ResumeContentUpdate(BaseModel):
    base_rev: int
    content: ResumeTailorerOutput


class ResumeVersionCreate(BaseModel):
    name: str = "New version"
    clone_active: bool = True


class ResumeVersionPatch(BaseModel):
    name: str | None = None
    make_active: bool | None = None


class EditRuleCreate(BaseModel):
    mode: Literal["always", "never"]
    text: str
    scope: Literal["resume", "cover_letter", "both"] = "resume"


class EditRuleResponse(BaseModel):
    id: str
    mode: str
    text: str
    scope: str
```

Confirm `from datetime import datetime` and `from typing import Literal` are already imported at the top of `schemas.py` (they are used by existing schemas); if `datetime` is missing, add `from datetime import datetime`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas/test_resume_document_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/schemas.py tests/test_schemas/test_resume_document_schemas.py
git commit -m "feat(resume-editor): resume document + rule schemas"
```

---

### Task 3: Deterministic master seed from profile

**Files:**
- Create: `backend/services/resume_seed.py`
- Test: `tests/test_services/test_resume_seed.py`

**Interfaces:**
- Consumes: `ProfileReviewData` (already in `schemas.py`: `target_role, key_skills[], projects[ProfileReviewProject{name,description,highlights[]}], experience[ProfileReviewExperience{company,role,dates,highlights[]}], education[ProfileReviewEducation{institution,degree,field_of_study,dates}]`), `Profile.profile_review_data` (JSON Text).
- Produces: `seed_resume_content(profile: Profile) -> ResumeTailorerOutput` — pure mapping, no LLM.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_resume_seed.py
import json

from backend.models import Profile
from backend.schemas import ProfileReviewData
from backend.services.resume_seed import seed_resume_content


def _profile_with(review: ProfileReviewData) -> Profile:
    return Profile(
        yaml_data="x", merged_profile="m",
        profile_review_data=review.model_dump_json(),
    )


def test_seed_maps_profile_sections():
    review = ProfileReviewData(
        target_role="Senior Backend Engineer",
        key_skills=["Python", "FastAPI"],
        experience=[{"company": "Acme", "role": "SWE", "dates": "2022-2024",
                     "highlights": ["Built X", "Owned Y"]}],
        projects=[{"name": "JobFit", "description": "AI app", "highlights": ["pipeline"]}],
        education=[{"institution": "PES", "degree": "BSc", "field_of_study": "CS",
                    "dates": "2017-2021"}],
    )
    out = seed_resume_content(_profile_with(review))
    assert out.headline == "Senior Backend Engineer"
    assert out.skills == ["Python", "FastAPI"]
    assert out.experience[0].company == "Acme"
    assert out.experience[0].bullets == ["Built X", "Owned Y"]
    assert out.projects[0].name == "JobFit"
    assert out.projects[0].bullets == ["pipeline"]
    assert out.education[0].institution == "PES"


def test_seed_handles_empty_review():
    out = seed_resume_content(Profile(yaml_data="x", merged_profile="m", profile_review_data="{}"))
    assert out.headline == ""
    assert out.experience == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_resume_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.services.resume_seed`.

- [ ] **Step 3: Implement the seed**

```python
# backend/services/resume_seed.py
from __future__ import annotations

import json

from backend.models import Profile
from backend.schemas import (
    ProfileReviewData,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeProjectItem,
    ResumeTailorerOutput,
)


def seed_resume_content(profile: Profile) -> ResumeTailorerOutput:
    """Deterministically map the user's reviewed profile into a base resume.

    No LLM: the master resume is a curated *view* of the profile, editable after.
    """
    raw = profile.profile_review_data or "{}"
    review = ProfileReviewData.model_validate(json.loads(raw))

    experience = [
        ResumeExperienceItem(
            company=e.company or None,
            role=e.role or None,
            dates=e.dates or None,
            bullets=list(e.highlights),
        )
        for e in review.experience
    ]
    projects = [
        ResumeProjectItem(name=p.name, description=p.description or None, bullets=list(p.highlights))
        for p in review.projects
    ]
    education = [
        ResumeEducationItem(
            institution=ed.institution or None,
            degree=(f"{ed.degree}, {ed.field_of_study}".strip(", ") if ed.field_of_study else ed.degree)
            or None,
            dates=ed.dates or None,
        )
        for ed in review.education
    ]
    return ResumeTailorerOutput(
        headline=review.target_role or "",
        summary="",
        skills=list(review.key_skills),
        experience=experience,
        projects=projects,
        education=education,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_resume_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/resume_seed.py tests/test_services/test_resume_seed.py
git commit -m "feat(resume-editor): deterministic master resume seed from profile"
```

---

### Task 4: Document service — CAS writes, versions, active invariant, revisions/undo

**Files:**
- Create: `backend/services/resume_document.py`
- Create: `backend/services/resume_errors.py`
- Test: `tests/test_services/test_resume_document_service.py`

**Interfaces:**
- Consumes: `ResumeDocument`, `ResumeDocumentRevision` (Task 1); `ResumeTailorerOutput`, `seed_resume_content` (Task 3).
- Produces:
  - `class StaleRevError(Exception)` with attribute `current: ResumeDocument`.
  - `async get_or_seed_master(db, user_id, profile) -> ResumeDocument`
  - `async list_master_versions(db, user_id) -> list[ResumeDocument]`
  - `async create_version(db, user_id, name, clone_from: ResumeDocument | None) -> ResumeDocument`
  - `async set_active(db, user_id, doc_id) -> ResumeDocument`
  - `async rename_version(db, doc: ResumeDocument, name) -> ResumeDocument`
  - `async delete_version(db, user_id, doc: ResumeDocument) -> None`
  - `async apply_write(db, doc, new_content: ResumeTailorerOutput, base_rev, source, summary=None) -> ResumeDocument` — raises `StaleRevError` on `base_rev != doc.rev`; bumps `rev`, snapshots, prunes to 50.
  - `async undo(db, doc, base_rev) -> ResumeDocument` / `async redo(db, doc, base_rev) -> ResumeDocument`
  - `REVISION_LIMIT = 50`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_resume_document_service.py
import json

import pytest

from backend.models import Profile, ResumeDocument
from backend.schemas import ResumeTailorerOutput
from backend.services import resume_document as svc
from tests.factories import make_user


async def _master(db, user_id) -> ResumeDocument:
    profile = Profile(user_id=user_id, yaml_data="x", merged_profile="m", profile_review_data="{}")
    db.add(profile)
    await db.flush()
    return await svc.get_or_seed_master(db, user_id, profile)


async def test_seed_creates_single_active_default(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    assert doc.name == "Default" and doc.is_active is True and doc.rev == 0
    # calling again returns the same row, not a second one
    versions = await svc.list_master_versions(db_session, user.id)
    assert len(versions) == 1


async def test_apply_write_bumps_rev_and_snapshots(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    updated = await svc.apply_write(
        db_session, doc, ResumeTailorerOutput(headline="New"), base_rev=0, source="inline"
    )
    assert updated.rev == 1
    assert json.loads(updated.content_json)["headline"] == "New"


async def test_stale_base_rev_raises_and_does_not_clobber(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(db_session, doc, ResumeTailorerOutput(headline="A"), base_rev=0, source="inline")
    with pytest.raises(svc.StaleRevError):
        await svc.apply_write(
            db_session, doc, ResumeTailorerOutput(headline="B"), base_rev=0, source="chat"
        )
    assert json.loads(doc.content_json)["headline"] == "A"  # unchanged


async def test_set_active_is_exclusive(db_session):
    user = await make_user(db_session)
    await _master(db_session, user.id)
    v2 = await svc.create_version(db_session, user.id, "Aggressive", clone_from=None)
    switched = await svc.set_active(db_session, user.id, v2.id)
    assert switched.is_active is True
    actives = [v for v in await svc.list_master_versions(db_session, user.id) if v.is_active]
    assert len(actives) == 1 and actives[0].id == v2.id


async def test_undo_restores_prior_content(db_session):
    user = await make_user(db_session)
    doc = await _master(db_session, user.id)
    await svc.apply_write(db_session, doc, ResumeTailorerOutput(headline="V1"), base_rev=0, source="inline")
    undone = await svc.undo(db_session, doc, base_rev=1)
    assert json.loads(undone.content_json)["headline"] == ""  # back to seed content
    assert undone.rev == 2  # non-destructive: undo is a new rev
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_resume_document_service.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.services.resume_document`.

- [ ] **Step 3: Implement the error type**

```python
# backend/services/resume_errors.py
from __future__ import annotations

from typing import Any


class StaleRevError(Exception):
    """Raised when a write's base_rev no longer matches the document (concurrent edit)."""

    def __init__(self, current: Any) -> None:
        super().__init__("resume document was modified by a concurrent edit")
        self.current = current
```

- [ ] **Step 4: Implement the service**

```python
# backend/services/resume_document.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Profile, ResumeDocument, ResumeDocumentRevision
from backend.schemas import ResumeTailorerOutput
from backend.services.resume_errors import StaleRevError
from backend.services.resume_seed import seed_resume_content

REVISION_LIMIT = 50


async def _snapshot(
    db: AsyncSession, doc: ResumeDocument, source: str, summary: str | None
) -> None:
    db.add(
        ResumeDocumentRevision(
            document_id=doc.id,
            doc_kind="resume",
            rev=doc.rev,
            content_json=doc.content_json,
            source=source,
            summary=summary,
        )
    )
    rows = (
        (
            await db.execute(
                select(ResumeDocumentRevision)
                .where(ResumeDocumentRevision.document_id == doc.id)
                .order_by(ResumeDocumentRevision.rev.desc())
            )
        )
        .scalars()
        .all()
    )
    for stale in rows[REVISION_LIMIT:]:
        await db.delete(stale)


async def list_master_versions(db: AsyncSession, user_id: str) -> list[ResumeDocument]:
    return list(
        (
            await db.execute(
                select(ResumeDocument)
                .where(ResumeDocument.user_id == user_id, ResumeDocument.kind == "master")
                .order_by(ResumeDocument.created_at)
            )
        )
        .scalars()
        .all()
    )


async def get_or_seed_master(
    db: AsyncSession, user_id: str, profile: Profile
) -> ResumeDocument:
    existing = await list_master_versions(db, user_id)
    if existing:
        active = next((d for d in existing if d.is_active), existing[0])
        return active
    content = seed_resume_content(profile)
    doc = ResumeDocument(
        user_id=user_id,
        kind="master",
        name="Default",
        content_json=content.model_dump_json(),
        is_active=True,
        rev=0,
    )
    db.add(doc)
    await db.flush()
    await _snapshot(db, doc, source="seed", summary=None)
    await db.commit()
    await db.refresh(doc)
    return doc


async def create_version(
    db: AsyncSession, user_id: str, name: str, clone_from: ResumeDocument | None
) -> ResumeDocument:
    content_json = clone_from.content_json if clone_from is not None else "{}"
    doc = ResumeDocument(
        user_id=user_id, kind="master", name=name, content_json=content_json, is_active=False, rev=0
    )
    db.add(doc)
    await db.flush()
    await _snapshot(db, doc, source="seed", summary=None)
    await db.commit()
    await db.refresh(doc)
    return doc


async def set_active(db: AsyncSession, user_id: str, doc_id: str) -> ResumeDocument:
    versions = await list_master_versions(db, user_id)
    target = next((d for d in versions if d.id == doc_id), None)
    if target is None:
        raise KeyError(doc_id)
    for d in versions:
        d.is_active = d.id == doc_id
    await db.commit()
    await db.refresh(target)
    return target


async def rename_version(db: AsyncSession, doc: ResumeDocument, name: str) -> ResumeDocument:
    doc.name = name
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_version(db: AsyncSession, user_id: str, doc: ResumeDocument) -> None:
    was_active = doc.is_active
    await db.delete(doc)
    await db.flush()
    if was_active:
        remaining = await list_master_versions(db, user_id)
        if remaining:
            newest = max(remaining, key=lambda d: d.updated_at)
            newest.is_active = True
    await db.commit()


async def apply_write(
    db: AsyncSession,
    doc: ResumeDocument,
    new_content: ResumeTailorerOutput,
    base_rev: int,
    source: str,
    summary: str | None = None,
) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    await _snapshot(db, doc, source=source, summary=summary)  # snapshot the pre-write state
    doc.content_json = new_content.model_dump_json()
    doc.rev = doc.rev + 1
    await db.commit()
    await db.refresh(doc)
    return doc


async def _neighbour_content(db: AsyncSession, doc: ResumeDocument, target_rev: int) -> str | None:
    row = (
        await db.execute(
            select(ResumeDocumentRevision).where(
                ResumeDocumentRevision.document_id == doc.id,
                ResumeDocumentRevision.rev == target_rev,
            )
        )
    ).scalar_one_or_none()
    return row.content_json if row is not None else None


async def undo(db: AsyncSession, doc: ResumeDocument, base_rev: int) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    prior = await _neighbour_content(db, doc, doc.rev - 1)
    if prior is None:
        return doc  # nothing to undo
    content = ResumeTailorerOutput.model_validate_json(prior)
    return await apply_write(db, doc, content, base_rev=doc.rev, source="undo")


async def redo(db: AsyncSession, doc: ResumeDocument, base_rev: int) -> ResumeDocument:
    if base_rev != doc.rev:
        raise StaleRevError(current=doc)
    nxt = await _neighbour_content(db, doc, doc.rev + 1)
    if nxt is None:
        return doc
    content = ResumeTailorerOutput.model_validate_json(nxt)
    return await apply_write(db, doc, content, base_rev=doc.rev, source="undo")
```

- [ ] **Step 5: Run the service tests to verify they pass**

Run: `pytest tests/test_services/test_resume_document_service.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/resume_document.py backend/services/resume_errors.py tests/test_services/test_resume_document_service.py
git commit -m "feat(resume-editor): document service with CAS writes, versions, undo"
```

---

### Task 5: Config settings + `routes/resume.py` + registration

**Files:**
- Modify: `backend/config.py` (add settings)
- Create: `backend/routes/resume.py`
- Modify: `backend/main.py` (import + register router)
- Test: `tests/test_routes/test_resume.py`

**Interfaces:**
- Consumes: service functions from Task 4; schemas from Task 2; `get_current_user`, `get_db`; `get_owned_profile` from `backend.services.profile_builder`.
- Produces: routes listed below, mounted at `settings.api_prefix`.

- [ ] **Step 1: Add config settings**

In `backend/config.py`, inside `class Settings`, add (near the other model fields):

```python
    resume_model: str = "claude-opus-4-8"
    resume_model_fallback: str = "claude-sonnet-4-6"
    resume_faithfulness_judge_enabled: bool = False
```

- [ ] **Step 2: Write the failing route test**

```python
# tests/test_routes/test_resume.py
from __future__ import annotations

import backend.models  # noqa: F401
from backend.services.auth_service import get_current_user
from tests.factories import make_profile, make_user


async def test_get_resume_seeds_master(app_client, db_session):
    # app_client is authenticated as the test user; ensure a profile exists for them.
    from backend.main import app  # noqa: PLC0415

    user_id = None
    # The test harness authenticates as a fixed user id; fetch it via the dependency override.
    for dep, override in app.dependency_overrides.items():
        if dep is get_current_user:
            user_id = (await override()).id
    assert user_id
    await make_profile(db_session, user_id=user_id, profile_review_data="{}")
    await db_session.commit()

    resp = await app_client.get("/api/resume")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "master" and body["is_active"] is True and body["rev"] == 0


async def test_patch_content_enforces_base_rev(app_client, db_session):
    from backend.main import app  # noqa: PLC0415

    user_id = None
    for dep, override in app.dependency_overrides.items():
        if dep is get_current_user:
            user_id = (await override()).id
    await make_profile(db_session, user_id=user_id, profile_review_data="{}")
    await db_session.commit()

    doc = (await app_client.get("/api/resume")).json()
    good = await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Engineer"}},
    )
    assert good.status_code == 200 and good.json()["rev"] == 1

    stale = await app_client.patch(
        f"/api/resume/{doc['id']}/content",
        json={"base_rev": 0, "content": {"headline": "Clobber"}},
    )
    assert stale.status_code == 409  # concurrency guard fired


async def test_resume_requires_auth(unauth_client):
    resp = await unauth_client.get("/api/resume")
    assert resp.status_code in (401, 403)
```

> Note: `unauth_client` is the existing fixture used by other route tests for the auth check — confirm its name in `tests/test_routes/conftest.py` and match it (e.g. some suites call it `client_no_auth`). Use whatever the sibling tests use.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_routes/test_resume.py -v`
Expected: FAIL (404s — router not mounted).

- [ ] **Step 4: Implement the router**

```python
# backend/routes/resume.py
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ResumeDocument, ResumeEditRule, User
from backend.schemas import (
    EditRuleCreate,
    EditRuleResponse,
    ResumeContentUpdate,
    ResumeDocumentResponse,
    ResumeTailorerOutput,
    ResumeVersionCreate,
    ResumeVersionPatch,
    ResumeVersionSummary,
)
from backend.services import resume_document as svc
from backend.services.auth_service import get_current_user
from backend.services.profile_builder import get_owned_profile
from backend.services.resume_errors import StaleRevError

router = APIRouter(tags=["resume"])


def _to_response(doc: ResumeDocument) -> ResumeDocumentResponse:
    return ResumeDocumentResponse(
        id=doc.id,
        kind=doc.kind,
        name=doc.name,
        is_active=doc.is_active,
        rev=doc.rev,
        content=ResumeTailorerOutput.model_validate(json.loads(doc.content_json or "{}")),
        updated_at=doc.updated_at,
    )


async def _owned_master(db: AsyncSession, doc_id: str, user_id: str) -> ResumeDocument:
    doc = (
        await db.execute(
            select(ResumeDocument).where(
                ResumeDocument.id == doc_id,
                ResumeDocument.user_id == user_id,
                ResumeDocument.kind == "master",
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Resume version not found")
    return doc


@router.get("/resume", response_model=ResumeDocumentResponse)
async def get_active_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    profile = await get_owned_profile(db, current_user.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="Build your profile before creating a resume")
    doc = await svc.get_or_seed_master(db, current_user.id, profile)
    return _to_response(doc)


@router.get("/resume/versions", response_model=list[ResumeVersionSummary])
async def list_versions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResumeVersionSummary]:
    rows = await svc.list_master_versions(db, current_user.id)
    return [
        ResumeVersionSummary(
            id=d.id, name=d.name, is_active=d.is_active, rev=d.rev, updated_at=d.updated_at
        )
        for d in rows
    ]


@router.post("/resume/versions", response_model=ResumeDocumentResponse)
async def create_version(
    data: ResumeVersionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    clone = None
    if data.clone_active:
        versions = await svc.list_master_versions(db, current_user.id)
        clone = next((d for d in versions if d.is_active), None)
    doc = await svc.create_version(db, current_user.id, data.name, clone_from=clone)
    return _to_response(doc)


@router.patch("/resume/versions/{doc_id}", response_model=ResumeDocumentResponse)
async def patch_version(
    doc_id: str,
    data: ResumeVersionPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    if data.name is not None:
        doc = await svc.rename_version(db, doc, data.name)
    if data.make_active:
        doc = await svc.set_active(db, current_user.id, doc_id)
    return _to_response(doc)


@router.delete("/resume/versions/{doc_id}", status_code=204)
async def delete_version(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    doc = await _owned_master(db, doc_id, current_user.id)
    await svc.delete_version(db, current_user.id, doc)
    return Response(status_code=204)


@router.patch("/resume/{doc_id}/content", response_model=ResumeDocumentResponse)
async def patch_content(
    doc_id: str,
    data: ResumeContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.apply_write(
            db, doc, data.content, base_rev=data.base_rev, source="inline"
        )
    except StaleRevError as exc:
        raise HTTPException(status_code=409, detail="Resume changed; reload and retry") from exc
    return _to_response(doc)


@router.post("/resume/{doc_id}/undo", response_model=ResumeDocumentResponse)
async def undo_content(
    doc_id: str,
    base_rev: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.undo(db, doc, base_rev=base_rev)
    except StaleRevError as exc:
        raise HTTPException(status_code=409, detail="Resume changed; reload and retry") from exc
    return _to_response(doc)


@router.post("/resume/{doc_id}/restore", response_model=ResumeDocumentResponse)
async def restore_content(
    doc_id: str,
    base_rev: int,
    target_rev: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    # Cursor-driven restore: the frontend performs REDO (and jump-to-revision) by passing the
    # target rev. A parameterless server-side redo cannot work against an append-only log.
    doc = await _owned_master(db, doc_id, current_user.id)
    try:
        doc = await svc.restore_revision(db, doc, base_rev=base_rev, target_rev=target_rev)
    except StaleRevError as exc:
        raise HTTPException(status_code=409, detail="Resume changed; reload and retry") from exc
    return _to_response(doc)


@router.get("/resume/{doc_id}/revisions")
async def list_revisions(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    # The frontend's undo-cursor source of truth (design §3.4).
    doc = await _owned_master(db, doc_id, current_user.id)
    revs = await svc.list_revisions(db, doc)
    return [
        {"rev": r.rev, "source": r.source, "summary": r.summary, "created_at": r.created_at.isoformat()}
        for r in revs
    ]


@router.get("/resume/rules", response_model=list[EditRuleResponse])
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EditRuleResponse]:
    rows = (
        (
            await db.execute(
                select(ResumeEditRule)
                .where(ResumeEditRule.user_id == current_user.id)
                .order_by(ResumeEditRule.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        EditRuleResponse(id=r.id, mode=r.mode, text=r.text, scope=r.scope) for r in rows
    ]


@router.post("/resume/rules", response_model=EditRuleResponse)
async def add_rule(
    data: EditRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EditRuleResponse:
    row = ResumeEditRule(
        user_id=current_user.id, mode=data.mode, text=data.text, scope=data.scope
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return EditRuleResponse(id=row.id, mode=row.mode, text=row.text, scope=row.scope)


@router.delete("/resume/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = (
        await db.execute(
            select(ResumeEditRule).where(
                ResumeEditRule.id == rule_id, ResumeEditRule.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Register the router in `main.py`**

Add the import alongside the other route imports (matching their style) and register it next to `targets_router`:

```python
from backend.routes.resume import router as resume_router
# ...
app.include_router(resume_router, prefix=settings.api_prefix)
```

Confirm `get_owned_profile` exists in `backend/services/profile_builder.py` (it is already imported by `routes/history.py`). If its signature differs (e.g. returns `Profile | None`), keep the `None` guard in `get_active_resume`.

- [ ] **Step 6: Run the route tests to verify they pass**

Run: `pytest tests/test_routes/test_resume.py -v`
Expected: PASS (seed, base_rev 409, auth).

- [ ] **Step 7: Full check**

Run: `make check`
Expected: fmt clean, ruff + mypy clean, tests pass (≥70% coverage gate holds).

- [ ] **Step 8: Commit**

```bash
git add backend/config.py backend/routes/resume.py backend/main.py tests/test_routes/test_resume.py
git commit -m "feat(resume-editor): resume + rules routes with concurrency-guarded writes"
```

---

## Self-Review

**Spec coverage (Plan 1 scope = build-sequence §13 items 1–2, plus rules table and config):**
- §3.1 `resume_documents` + `rev` → Task 1 ✓
- §3.2 `resume_edit_rules` → Task 1 (model) + Task 5 (CRUD) ✓
- §3.3 `cover_letter_documents` table exists → Task 1 ✓ (chat/UI deferred to Plans 2/6)
- §3.4 `resume_document_revisions` + undo/redo → Task 1 (table) + Task 4 (undo/redo) ✓
- §3.5 migration → Task 1 ✓
- §4 config settings (`resume_model`, `resume_model_fallback`, `resume_faithfulness_judge_enabled`) → Task 5 ✓
- §5.1 direct-edit persistence (PATCH content) → Task 5 ✓
- §5.3 `rev` CAS, 409, revision snapshots, undo/redo → Task 4 + Task 5 ✓
- §3.1 master seeded deterministically from profile → Task 3 ✓
- §10 API (versions CRUD, content PATCH w/ base_rev, undo/restore + revisions list, rules) → Task 5 ✓
- Deferred by design to later plans: chat endpoint (§5.2/Plan 2), faithfulness warnings (§9/Plan 3), master-as-base (§7/Plan 4), download wiring + preview (§6/Plan 5), cover-letter chat/UI (Plan 6).

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `apply_write(db, doc, content, base_rev, source, summary=None)` signature matches its callers in Task 5; `StaleRevError.current` set in Task 3-error-module and read in Task 5 handlers; `ResumeTailorerOutput` used consistently as the content model across seed/service/routes; `get_or_seed_master(db, user_id, profile)` arity matches route call.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-resume-editor-01-backend-foundation.md`. Plans 2–6 (chat agent, faithfulness, master-as-base, frontend, cover-letter) are written after this one lands, each depending on the interfaces produced here.
