from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import Profile, User
from backend.schemas import ProfileResponse
from backend.services.auth_service import get_current_user
from backend.services.profile_builder import build_profile, get_or_build_profile

router = APIRouter(tags=["profile"])


def _profile_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse.model_validate(profile)


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
    """Rebuild the profile from YAML + CV."""
    profile = await build_profile(db, user_id=current_user.id)
    return _profile_response(profile)


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
