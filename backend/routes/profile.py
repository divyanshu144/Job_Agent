from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import Profile, User
from backend.schemas import GitHubRefreshResponse, ProfileResponse, ProfileStatusResponse
from backend.services.auth_service import get_current_user
from backend.services.profile_builder import (
    build_profile,
    get_or_build_profile,
    refresh_github_cache,
)

router = APIRouter(tags=["profile"])


def _profile_response(profile: Profile) -> ProfileResponse:
    """Build ProfileResponse, adding warnings when GitHub cache is empty."""
    resp = ProfileResponse.model_validate(profile)
    if profile.github_last_fetched_at is None:
        resp.warnings = ["GitHub data not yet synced. Use Refresh GitHub to populate."]
    return resp


@router.get("/profile/status", response_model=ProfileStatusResponse)
async def get_profile_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileStatusResponse:
    profile = await get_or_build_profile(db, user_id=current_user.id)
    stale_after = timedelta(days=settings.github_stale_days)
    now = datetime.utcnow()

    github_is_stale = profile.github_last_fetched_at is None or (
        now - profile.github_last_fetched_at
    ) > stale_after

    return ProfileStatusResponse(
        profile_last_built_at=profile.last_refreshed_at,
        github_last_fetched_at=profile.github_last_fetched_at,
        github_is_stale=github_is_stale,
        github_stale_after_days=settings.github_stale_days,
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await get_or_build_profile(db, user_id=current_user.id)
    return _profile_response(profile)


@router.post("/profile/refresh", response_model=ProfileResponse)
async def refresh_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Refresh YAML + CV only. Uses whatever is currently in github_cache."""
    profile = await build_profile(db, user_id=current_user.id)
    return _profile_response(profile)


@router.post("/profile/refresh/github", response_model=GitHubRefreshResponse)
async def refresh_github(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GitHubRefreshResponse:
    """Fetch all repos from GitHub, update cache, rebuild merged_profile."""
    profile, repos_updated = await refresh_github_cache(db, user_id=current_user.id)
    assert profile.github_last_fetched_at is not None
    return GitHubRefreshResponse(
        repos_updated=repos_updated,
        github_last_fetched_at=profile.github_last_fetched_at,
        profile=_profile_response(profile),
    )


@router.post("/profile/cv", response_model=ProfileResponse)
async def upload_cv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    cv_path = Path(settings.cv_path)
    cv_path.parent.mkdir(parents=True, exist_ok=True)
    cv_path.write_bytes(contents)
    profile = await build_profile(db, user_id=current_user.id)
    return _profile_response(profile)
