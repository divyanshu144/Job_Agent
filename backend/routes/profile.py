from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Profile, User
from backend.schemas import ProfileResponse
from backend.services.auth_service import get_current_user
from backend.services.cv_parser import extract_text_from_docx_bytes, extract_text_from_pdf_bytes
from backend.services.profile_builder import (
    build_profile,
    build_profile_from_text,
    get_or_build_profile,
)

router = APIRouter(tags=["profile"])

_PDF_TYPES = {"application/pdf", "application/octet-stream"}
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIN_EXTRACTED_CHARS = 20


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
    existing = (
        await db.execute(
            select(Profile)
            .where(Profile.user_id == current_user.id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    profile = await build_profile(
        db,
        user_id=current_user.id,
        cv_text=existing.cv_text if existing is not None else "",
    )
    return _profile_response(profile)


@router.post("/profile/cv", response_model=ProfileResponse)
async def upload_cv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    filename = file.filename or ""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    extractor: Callable[[bytes], Awaitable[str]]
    if suffix == "docx" or file.content_type == _DOCX_TYPE:
        extractor = extract_text_from_docx_bytes
    elif suffix == "pdf" or file.content_type in _PDF_TYPES:
        extractor = extract_text_from_pdf_bytes
    else:
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are accepted")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    cv_text = await extractor(contents)
    if len(cv_text.strip()) < _MIN_EXTRACTED_CHARS:
        raise HTTPException(
            status_code=400,
            detail="Could not extract enough resume text from the uploaded file",
        )
    existing = (
        await db.execute(
            select(Profile)
            .where(Profile.user_id == current_user.id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    yaml_text = (
        existing.yaml_data
        if existing is not None
        else (await get_or_build_profile(db, current_user.id)).yaml_data
    )
    profile = await build_profile_from_text(
        db,
        yaml_text=yaml_text,
        cv_text=cv_text,
        user_id=current_user.id,
    )
    return _profile_response(profile)
