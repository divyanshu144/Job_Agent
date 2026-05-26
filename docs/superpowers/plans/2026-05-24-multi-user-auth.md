# Multi-User Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add invite-only email+password authentication so multiple team members can share the job discovery pool while each having their own profile, analyses, and saved jobs.

**Architecture:** JWT tokens stored in httpOnly cookies (set by FastAPI, never touched by JS). First user to register becomes admin with no invite required; subsequent registrations require a valid invite token created by an admin. Job discovery and scoring remain shared (one pool visible to all users). Saved jobs become per-user via a `saved_jobs` join table replacing the `Job.saved` boolean. All existing routes are protected by a `get_current_user` FastAPI dependency.

**Tech Stack:** `python-jose[cryptography]` (JWT), `passlib[bcrypt]` (password hashing), React Context API (auth state), React Router protected routes.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add `python-jose[cryptography]`, `passlib[bcrypt]` |
| `backend/config.py` | Modify | Add `jwt_secret`, `jwt_expire_minutes` |
| `backend/models.py` | Modify | Add `User`, `InviteToken`, `SavedJob` models; add `user_id` to `Profile` and `Analysis`; keep `Job.saved` column in DB but remove from ORM |
| `backend/schemas.py` | Modify | Add `UserCreate`, `UserLogin`, `UserResponse`, `InviteCreate`, `InviteResponse` |
| `backend/services/auth_service.py` | Create | Password hashing, JWT encode/decode, `get_current_user` dependency |
| `backend/routes/auth.py` | Create | `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/invite` |
| `backend/routes/profile.py` | Modify | Require `current_user`; scope profile lookup to `user_id` |
| `backend/routes/analyse.py` | Modify | Require `current_user`; set `user_id` on Analysis |
| `backend/routes/discovery.py` | Modify | Require `current_user` for save/saved endpoints; use `SavedJob` table |
| `backend/routes/history.py` | Modify | Require `current_user`; filter analyses by `user_id` |
| `backend/services/profile_builder.py` | Modify | Accept `user_id`; scope DB lookups |
| `backend/services/discovery.py` | Modify | `_run_discovery_task` uses first active user's profile when no user specified |
| `backend/main.py` | Modify | Include auth router |
| `scripts/migrate.py` | Modify | Add steps for `users`, `invite_tokens`, `saved_jobs` tables; add `user_id` to `profiles` and `analyses` |
| `frontend/src/types/index.ts` | Modify | Add `User` interface |
| `frontend/src/api/client.ts` | Modify | Add auth methods; propagate `credentials: "include"` for cookies |
| `frontend/src/context/AuthContext.tsx` | Create | `AuthProvider`, `useAuth` hook — stores `User \| null` |
| `frontend/src/pages/Login.tsx` | Create | Email + password form |
| `frontend/src/pages/Register.tsx` | Create | Email + password + invite token form |
| `frontend/src/components/ProtectedRoute.tsx` | Create | Redirects to `/login` if not authenticated |
| `frontend/src/App.tsx` | Modify | Wrap with `AuthProvider`; add `/login`, `/register` routes; protect existing routes |

---

### Task 1: Install dependencies + config

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/config.py`

- [ ] **Step 1: Add packages to requirements.txt**

Append to `requirements.txt`:
```
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

- [ ] **Step 2: Install packages**

```bash
pip install "python-jose[cryptography]>=3.3.0" "passlib[bcrypt]>=1.7.4"
```
Expected: Successfully installed.

- [ ] **Step 3: Add JWT settings to config.py**

```python
# backend/config.py — full file replacement
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


settings = Settings()
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt backend/config.py
git commit -m "feat: add JWT/bcrypt deps and config for auth"
```

---

### Task 2: DB models — User, InviteToken, SavedJob

**Files:**
- Modify: `backend/models.py`
- Modify: `scripts/migrate.py`

- [ ] **Step 1: Add models to models.py**

Add these classes to `backend/models.py` (after `GithubCache`, before `DiscoveryRun`):

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class InviteToken(Base):
    __tablename__ = "invite_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    used_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

Also add `user_id` nullable FK to `Profile` and `Analysis`:

In `Profile` class, add:
```python
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, default=None)
```

In `Analysis` class, add:
```python
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True, default=None)
```

Remove `saved: Mapped[bool]` from `Job` class (keep the column in SQLite — SQLite can't drop columns — but remove it from the ORM).

- [ ] **Step 2: Add migration steps to scripts/migrate.py**

After the existing Step 10 (`saved` column), add:

```python
    # 11. Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            is_active       INTEGER NOT NULL DEFAULT 1,
            is_admin        INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    print("✓ users table ready")

    # 12. Create invite_tokens table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invite_tokens (
            id          TEXT PRIMARY KEY,
            token       TEXT NOT NULL UNIQUE,
            email       TEXT,
            created_by  TEXT NOT NULL REFERENCES users(id),
            used_by     TEXT REFERENCES users(id),
            expires_at  TIMESTAMP NOT NULL,
            used_at     TIMESTAMP
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_invite_tokens_token ON invite_tokens (token)")
    print("✓ invite_tokens table ready")

    # 13. Create saved_jobs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_jobs (
            user_id  TEXT NOT NULL REFERENCES users(id),
            job_id   TEXT NOT NULL REFERENCES jobs(id),
            saved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (user_id, job_id)
        )
    """)
    print("✓ saved_jobs table ready")

    # 14. Add user_id to profiles
    try:
        cur.execute("ALTER TABLE profiles ADD COLUMN user_id TEXT REFERENCES users(id)")
        print("✓ Added user_id to profiles")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- user_id on profiles already exists, skipping")
        else:
            raise

    # 15. Add user_id to analyses
    try:
        cur.execute("ALTER TABLE analyses ADD COLUMN user_id TEXT REFERENCES users(id)")
        print("✓ Added user_id to analyses")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- user_id on analyses already exists, skipping")
        else:
            raise
```

- [ ] **Step 3: Run migration**

```bash
python3 scripts/migrate.py
```
Expected output includes:
```
✓ users table ready
✓ invite_tokens table ready
✓ saved_jobs table ready
✓ Added user_id to profiles
✓ Added user_id to analyses
Migration complete.
```

- [ ] **Step 4: Commit**

```bash
git add backend/models.py scripts/migrate.py
git commit -m "feat: add User, InviteToken, SavedJob models and migration"
```

---

### Task 3: Auth service (JWT + password hashing + get_current_user)

**Files:**
- Create: `backend/services/auth_service.py`
- Create: `tests/test_services/test_auth_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_auth_service.py
import pytest
from backend.services.auth_service import hash_password, verify_password, create_access_token, decode_token


def test_hash_and_verify():
    hashed = hash_password("mysecret")
    assert verify_password("mysecret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_token(token) == "user-123"


def test_invalid_token_raises():
    from jose import JWTError
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_services/test_auth_service.py -v 2>&1 | head -20
```
Expected: ImportError — module doesn't exist yet.

- [ ] **Step 3: Create auth_service.py**

```python
# backend/services/auth_service.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    return str(payload["sub"])


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = decode_token(access_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_services/test_auth_service.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/auth_service.py tests/test_services/test_auth_service.py
git commit -m "feat: add auth service with JWT and bcrypt"
```

---

### Task 4: Auth schemas + auth routes

**Files:**
- Modify: `backend/schemas.py`
- Create: `backend/routes/auth.py`

- [ ] **Step 1: Add auth schemas to schemas.py**

Append to `backend/schemas.py`:

```python
class UserCreate(BaseModel):
    email: str
    password: str
    invite_token: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    is_admin: bool
    created_at: datetime


class InviteCreate(BaseModel):
    email: str | None = None  # if set, only this email can use the invite


class InviteResponse(BaseModel):
    invite_url: str
    token: str
    expires_at: datetime
```

- [ ] **Step 2: Create auth routes**

```python
# backend/routes/auth.py
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import InviteToken, User
from backend.schemas import InviteCreate, InviteResponse, UserCreate, UserLogin, UserResponse
from backend.services.auth_service import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["auth"])

_INVITE_EXPIRE_HOURS = 72


@router.post("/auth/register", response_model=UserResponse)
async def register(
    data: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    # Check if this is the first user (no invite required)
    user_count: int = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    is_first_user = user_count == 0

    if not is_first_user:
        if not data.invite_token:
            raise HTTPException(status_code=400, detail="Invite token required")
        invite = (
            await db.execute(
                select(InviteToken).where(
                    InviteToken.token == data.invite_token,
                    InviteToken.used_at.is_(None),
                    InviteToken.expires_at > datetime.now(timezone.utc),
                )
            )
        ).scalar_one_or_none()
        if invite is None:
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")
        if invite.email and invite.email.lower() != data.email.lower():
            raise HTTPException(status_code=400, detail="Invite token is for a different email")

    # Check email not already taken
    existing = (
        await db.execute(select(User).where(User.email == data.email.lower()))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        is_admin=is_first_user,
    )
    db.add(user)
    await db.flush()

    if not is_first_user and invite:
        invite.used_by = user.id
        invite.used_at = datetime.now(timezone.utc)

    await db.commit()

    token = create_access_token(user.id)
    response.set_cookie(
        "access_token", token,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return UserResponse.model_validate(user)


@router.post("/auth/login", response_model=UserResponse)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = (
        await db.execute(select(User).where(User.email == data.email.lower()))
    ).scalar_one_or_none()
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    token = create_access_token(user.id)
    response.set_cookie(
        "access_token", token,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return UserResponse.model_validate(user)


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/auth/invite", response_model=InviteResponse)
async def create_invite(
    data: InviteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_INVITE_EXPIRE_HOURS)
    invite = InviteToken(
        token=token,
        email=data.email,
        created_by=user.id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    return InviteResponse(
        invite_url=f"/register?token={token}",
        token=token,
        expires_at=expires_at,
    )
```

- [ ] **Step 3: Register auth router in main.py**

In `backend/main.py`, add:
```python
from backend.routes.auth import router as auth_router
```
And in the router includes:
```python
app.include_router(auth_router, prefix=settings.api_prefix)
```

- [ ] **Step 4: Commit**

```bash
git add backend/schemas.py backend/routes/auth.py backend/main.py
git commit -m "feat: add auth routes (register, login, logout, me, invite)"
```

---

### Task 5: Protect existing routes + wire user_id

**Files:**
- Modify: `backend/routes/profile.py`
- Modify: `backend/routes/analyse.py`
- Modify: `backend/routes/history.py`
- Modify: `backend/services/profile_builder.py`

- [ ] **Step 1: Protect profile routes and scope to user**

In `backend/routes/profile.py`, add `current_user` dependency to each route and pass `user_id`:

At the top add:
```python
from backend.models import User
from backend.services.auth_service import get_current_user
```

For each route handler, add `current_user: User = Depends(get_current_user)` as a parameter. Then pass `current_user.id` to the service calls that need it.

For example, `GET /profile` becomes:
```python
@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await get_or_build_profile(db, user_id=current_user.id)
    ...
```

- [ ] **Step 2: Update `get_or_build_profile` in profile_builder.py to accept user_id**

In `backend/services/profile_builder.py`, update `get_or_build_profile`:

```python
async def get_or_build_profile(db: AsyncSession, user_id: str | None = None) -> Profile:
    """Return the profile for the given user_id, or the first profile if user_id is None."""
    q = select(Profile)
    if user_id:
        q = q.where(Profile.user_id == user_id)
    profile = (await db.execute(q.order_by(Profile.last_refreshed_at.desc()))).scalar_one_or_none()
    if profile is None:
        profile = await _build_and_save_profile(db, user_id=user_id)
    return profile
```

Update `_build_and_save_profile` to accept and set `user_id`:
```python
async def _build_and_save_profile(db: AsyncSession, user_id: str | None = None) -> Profile:
    ...
    profile = Profile(yaml_data=..., cv_text=..., ..., user_id=user_id)
    ...
```

- [ ] **Step 3: Protect analyse routes**

In `backend/routes/analyse.py`, add `current_user` dependency and pass `user_id` when creating Analysis:

```python
from backend.models import User
from backend.services.auth_service import get_current_user

# On the POST /analyse route:
@router.post("/analyse")
async def analyse_job(
    body: AnalyseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    ...
```

In `orchestrator.py`, `run_evaluate_pipeline` should accept optional `user_id` and set it on the `Analysis` row:
```python
async def run_evaluate_pipeline(
    jd: str, db: AsyncSession, user_id: str | None = None
) -> AsyncGenerator[SSEEvent, None]:
    ...
    analysis = Analysis(
        jd_text=jd, profile_id=profile.id, partial=partial,
        evaluate_only=True, jd_hash=jd_hash, user_id=user_id
    )
```

- [ ] **Step 4: Protect history routes and filter by user**

In `backend/routes/history.py`, add `current_user` dependency and filter:

```python
from backend.models import User
from backend.services.auth_service import get_current_user

@router.get("/history", response_model=list[AnalysisSummary])
async def list_history(
    limit: int = Query(default=20, ge=0, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisSummary]:
    result = await db.execute(
        select(Analysis)
        .where(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(limit).offset(offset)
    )
    return [AnalysisSummary.model_validate(a) for a in result.scalars()]
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/profile.py backend/routes/analyse.py backend/routes/history.py backend/services/profile_builder.py backend/services/orchestrator.py
git commit -m "feat: protect existing routes with auth and scope data to current user"
```

---

### Task 6: Discovery routes — SavedJob replaces Job.saved

**Files:**
- Modify: `backend/routes/discovery.py`

- [ ] **Step 1: Update discovery routes to use SavedJob**

Replace the `toggle_save_job` and `get_saved_jobs` endpoints. Also update `get_discovery_feed` to compute `saved` per-user via LEFT JOIN.

In `backend/routes/discovery.py`:

Add imports:
```python
from sqlalchemy import and_
from backend.models import SavedJob, User
from backend.services.auth_service import get_current_user
```

Update `_job_row_to_item` to accept `is_saved`:
```python
def _job_row_to_item(row: object, is_saved: bool = False) -> DiscoveryFeedItem:
    return DiscoveryFeedItem(
        id=row.Job.id,  # type: ignore[attr-defined]
        title=row.Job.title,  # type: ignore[attr-defined]
        company=row.Job.company,  # type: ignore[attr-defined]
        location=row.Job.location,  # type: ignore[attr-defined]
        source_url=row.Job.source_url,  # type: ignore[attr-defined]
        sources=json.loads(row.Job.sources or "[]"),  # type: ignore[attr-defined]
        relevance_score=row.Job.relevance_score or 0,  # type: ignore[attr-defined]
        matched_profiles=json.loads(row.Job.matched_profiles or "[]"),  # type: ignore[attr-defined]
        analysis_id=row.analysis_id,  # type: ignore[attr-defined]
        state=row.Job.state,  # type: ignore[attr-defined]
        discovered_at=row.Job.discovered_at,  # type: ignore[attr-defined]
        saved=is_saved,
    )
```

Update `get_discovery_feed` to JOIN with `saved_jobs`:
```python
@router.get("/discovery/feed", response_model=DiscoveryFeedResponse)
async def get_discovery_feed(
    profile: str | None = Query(default=None),
    location: str | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryFeedResponse:
    base = (
        select(Job, Analysis.id.label("analysis_id"), SavedJob.user_id.label("saved_by"))
        .outerjoin(Analysis, Analysis.job_id == Job.id)
        .outerjoin(SavedJob, and_(SavedJob.job_id == Job.id, SavedJob.user_id == current_user.id))
        .where(Job.state == "scored")
        .where(Job.relevance_score >= min_score)
    )
    if profile:
        base = base.where(Job.matched_profiles.like(f'%"{profile}"%'))
    if location:
        base = base.where(Job.location.ilike(f"%{location}%"))

    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))).all()

    return DiscoveryFeedResponse(
        items=[_job_row_to_item(r, is_saved=r.saved_by is not None) for r in rows],
        total=total,
        has_more=offset + limit < total,
    )
```

Update `toggle_save_job` to use `SavedJob`:
```python
@router.patch("/discovery/jobs/{job_id}/save")
async def toggle_save_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = (
        await db.execute(
            select(SavedJob).where(SavedJob.user_id == current_user.id, SavedJob.job_id == job_id)
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        saved = False
    else:
        db.add(SavedJob(user_id=current_user.id, job_id=job_id))
        saved = True
    await db.commit()
    return {"id": job_id, "saved": saved}
```

Update `get_saved_jobs`:
```python
@router.get("/discovery/saved", response_model=DiscoveryFeedResponse)
async def get_saved_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryFeedResponse:
    base = (
        select(Job, Analysis.id.label("analysis_id"), SavedJob.user_id.label("saved_by"))
        .join(SavedJob, and_(SavedJob.job_id == Job.id, SavedJob.user_id == current_user.id))
        .outerjoin(Analysis, Analysis.job_id == Job.id)
    )
    total: int = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Job.relevance_score.desc()).limit(limit).offset(offset))).all()
    return DiscoveryFeedResponse(
        items=[_job_row_to_item(r, is_saved=True) for r in rows],
        total=total,
        has_more=offset + limit < total,
    )
```

Also protect `trigger_discovery`:
```python
@router.post("/discovery/run")
async def trigger_discovery(
    source: str = Query(default="hn"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    run_id = await run_discovery(source, db)
    return {"run_id": run_id}
```

- [ ] **Step 2: Commit**

```bash
git add backend/routes/discovery.py
git commit -m "feat: migrate saved jobs to per-user SavedJob table in discovery routes"
```

---

### Task 7: Frontend — types, API client, AuthContext

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/context/AuthContext.tsx`

- [ ] **Step 1: Add User type to types/index.ts**

Append to `frontend/src/types/index.ts`:
```typescript
export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
}
```

- [ ] **Step 2: Update api/client.ts — add credentials + auth methods**

Update the `get` helper and all `fetch` calls to include `credentials: "include"` (required for cookies):

```typescript
async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}
```

Also update all manual `fetch` calls (refreshProfile, uploadCv, refreshGithub, triggerDiscovery, saveJob) to include `credentials: "include"`.

Add auth API methods after the `saveJob` entry:
```typescript
  getMe: async (): Promise<User | null> => {
    try {
      return await get<User>("/auth/me");
    } catch {
      return null;
    }
  },
  login: async (email: string, password: string): Promise<User> => {
    const r = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      credentials: "include",
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(err.detail || "Login failed");
    }
    return r.json() as Promise<User>;
  },
  register: async (email: string, password: string, inviteToken?: string): Promise<User> => {
    const r = await fetch(`${BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, invite_token: inviteToken }),
      credentials: "include",
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Registration failed" }));
      throw new Error(err.detail || "Registration failed");
    }
    return r.json() as Promise<User>;
  },
  logout: async (): Promise<void> => {
    await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
  },
```

Update the import line to include `User`:
```typescript
import type { ..., User } from "../types";
```

- [ ] **Step 3: Create AuthContext.tsx**

```typescript
// frontend/src/context/AuthContext.tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { User } from "../types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, inviteToken?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getMe().then(setUser).finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const u = await api.login(email, password);
    setUser(u);
  }

  async function register(email: string, password: string, inviteToken?: string) {
    const u = await api.register(email, password, inviteToken);
    setUser(u);
  }

  async function logout() {
    await api.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/context/AuthContext.tsx
git commit -m "feat: add User type, auth API methods, and AuthContext"
```

---

### Task 8: Login + Register pages + ProtectedRoute

**Files:**
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/pages/Register.tsx`
- Create: `frontend/src/components/ProtectedRoute.tsx`

- [ ] **Step 1: Create Login.tsx**

```typescript
// frontend/src/pages/Login.tsx
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-xl border border-slate-200 p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Sign in</h1>
          <p className="text-sm text-slate-500 mt-1">JobFit Agent</p>
        </div>
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white text-sm font-semibold py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="text-xs text-slate-400 text-center">
          Have an invite?{" "}
          <Link to="/register" className="text-blue-600 hover:underline">Register</Link>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create Register.tsx**

```typescript
// frontend/src/pages/Register.tsx
import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get("token") ?? undefined;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(email, password, inviteToken);
      navigate("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-xl border border-slate-200 p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Create account</h1>
          {inviteToken ? (
            <p className="text-sm text-emerald-600 mt-1">You have a valid invite.</p>
          ) : (
            <p className="text-sm text-slate-500 mt-1">First user gets admin access.</p>
          )}
        </div>
        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-slate-700">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <p className="text-xs text-slate-400">Minimum 8 characters</p>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white text-sm font-semibold py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="text-xs text-slate-400 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-blue-600 hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create ProtectedRoute.tsx**

```typescript
// frontend/src/components/ProtectedRoute.tsx
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { ReactNode } from "react";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-6 text-slate-500">Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/pages/Register.tsx frontend/src/components/ProtectedRoute.tsx
git commit -m "feat: add Login, Register pages and ProtectedRoute component"
```

---

### Task 9: Update App.tsx + nav

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Rewrite App.tsx**

```typescript
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { Saved } from "./pages/Saved";
import { Discover } from "./pages/Discover";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium rounded-md ${isActive ? "bg-blue-100 text-blue-700" : "text-slate-600 hover:text-slate-900"}`;

function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  if (!user) return null;

  return (
    <nav className="border-b bg-white px-6 py-3 flex items-center gap-4">
      <span className="font-bold text-slate-900 mr-4">JobFit</span>
      <NavLink to="/" end className={link}>Profile</NavLink>
      <NavLink to="/analyse" className={link}>Analyse</NavLink>
      <NavLink to="/discover" className={link}>Discover</NavLink>
      <NavLink to="/saved" className={link}>Saved</NavLink>
      <div className="ml-auto flex items-center gap-3">
        <span className="text-xs text-slate-500">{user.email}</span>
        {user.is_admin && (
          <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100">admin</span>
        )}
        <button
          onClick={handleLogout}
          className="text-xs text-slate-500 hover:text-slate-800 px-2 py-1 border border-slate-200 rounded-md hover:border-slate-300 transition-colors"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen bg-slate-50">
          <Nav />
          <main className="py-8">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/" element={<ProtectedRoute><ProfileSetup /></ProtectedRoute>} />
              <Route path="/analyse" element={<ProtectedRoute><AnalyseJob /></ProtectedRoute>} />
              <Route path="/results/:id" element={<ProtectedRoute><Results /></ProtectedRoute>} />
              <Route path="/discover" element={<ProtectedRoute><Discover /></ProtectedRoute>} />
              <Route path="/saved" element={<ProtectedRoute><Saved /></ProtectedRoute>} />
            </Routes>
          </main>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/divyanshu/Desktop/Job_Ready_Agent/frontend && npx tsc --noEmit 2>&1
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wrap app in AuthProvider, protect routes, add user nav"
```

---

### Task 10: End-to-end smoke test

- [ ] **Step 1: Restart backend**

```bash
# Stop running server, then:
uvicorn backend.main:app --reload --port 8000
```

- [ ] **Step 2: Register first user (no invite needed)**

```bash
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password123"}' | python3 -m json.tool
```
Expected: `{"id": "...", "email": "admin@example.com", "is_admin": true, ...}`

- [ ] **Step 3: Verify /auth/me with cookie**

```bash
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt \
  http://localhost:8000/api/auth/me | python3 -m json.tool
```
Expected: same user object.

- [ ] **Step 4: Create an invite link**

```bash
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt \
  -X POST http://localhost:8000/api/auth/invite \
  -H "Content-Type: application/json" \
  -d '{"email": null}' | python3 -m json.tool
```
Expected: `{"invite_url": "/register?token=...", "token": "...", "expires_at": "..."}`

- [ ] **Step 5: Verify protected route rejects unauthenticated**

```bash
curl -s http://localhost:8000/api/profile
```
Expected: `{"detail": "Not authenticated"}` with status 401.

- [ ] **Step 6: Test login flow in browser**

Navigate to `http://localhost:5173` — should redirect to `/login`.
Log in with `admin@example.com` / `password123` — should land on Profile page with nav showing email and "admin" badge.
