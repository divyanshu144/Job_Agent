from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Profile, User
from backend.schemas import ProfileResponse, ProfileReviewResponse, ProfileReviewUpdate
from backend.services.auth_service import get_current_user
from backend.services.cv_parser import extract_text_from_docx_bytes, extract_text_from_pdf_bytes
from backend.services.profile_builder import (
    build_profile,
    build_profile_from_text,
    default_profile_yaml,
    parse_profile_review_data,
)

router = APIRouter(tags=["profile"])

_PDF_TYPES = {"application/pdf", "application/octet-stream"}
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIN_EXTRACTED_CHARS = 20


def _profile_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse.model_validate(profile)


async def _latest_user_profile(db: AsyncSession, user_id: str) -> Profile | None:
    return (
        await db.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.last_refreshed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _profile_review_response(profile: Profile) -> ProfileReviewResponse:
    return ProfileReviewResponse(
        profile_id=profile.id,
        review_data=parse_profile_review_data(profile.profile_review_data),
        review_status=profile.review_status,
        reviewed_at=profile.reviewed_at,
        has_cv_text=bool(profile.cv_text.strip()),
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """First visit with no owned row mints the per-user STARTER profile (same
    as /profile/review) — never the shared yaml/cv files (tenant boundary)."""
    profile = await _latest_user_profile(db, current_user.id)
    if profile is None:
        profile = await build_profile_from_text(
            db,
            yaml_text=default_profile_yaml(),
            cv_text="",
            user_id=current_user.id,
        )
        await db.commit()
        await db.refresh(profile)
    return _profile_response(profile)


@router.get("/profile/review", response_model=ProfileReviewResponse)
async def get_profile_review(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileReviewResponse:
    profile = await _latest_user_profile(db, current_user.id)
    if profile is None:
        profile = await build_profile_from_text(
            db,
            yaml_text=default_profile_yaml(),
            cv_text="",
            user_id=current_user.id,
        )
        await db.commit()
        await db.refresh(profile)
    return _profile_review_response(profile)


@router.put("/profile/review", response_model=ProfileReviewResponse)
async def update_profile_review(
    payload: ProfileReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileReviewResponse:
    existing = await _latest_user_profile(db, current_user.id)
    profile = await build_profile_from_text(
        db,
        yaml_text=existing.yaml_data if existing is not None else default_profile_yaml(),
        cv_text=existing.cv_text if existing is not None else "",
        user_id=current_user.id,
        profile_review_data=payload.review_data,
        review_status="saved",
        reviewed_at=datetime.now(timezone.utc),
    )
    await db.commit()
    await db.refresh(profile)
    return _profile_review_response(profile)


@router.post("/profile/refresh", response_model=ProfileResponse)
async def refresh_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Rebuild the profile. Admin rebuilds from the shared YAML file; a regular
    user rebuilds from their OWN existing data only (tenant boundary — the
    shared profile_yaml_path/cv_path serve admin only)."""
    existing = await _latest_user_profile(db, current_user.id)
    if current_user.is_admin:
        profile = await build_profile(
            db,
            user_id=current_user.id,
            cv_text=existing.cv_text if existing is not None else "",
            profile_review_data=existing.profile_review_data if existing is not None else "{}",
            review_status=existing.review_status if existing is not None else "draft",
            reviewed_at=existing.reviewed_at if existing is not None else None,
        )
    else:
        profile = await build_profile_from_text(
            db,
            yaml_text=existing.yaml_data if existing is not None else default_profile_yaml(),
            cv_text=existing.cv_text if existing is not None else "",
            user_id=current_user.id,
            profile_review_data=existing.profile_review_data if existing is not None else "{}",
            review_status=existing.review_status if existing is not None else "draft",
            reviewed_at=existing.reviewed_at if existing is not None else None,
        )
    await db.commit()
    await db.refresh(profile)
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
    existing = await _latest_user_profile(db, current_user.id)
    yaml_text = existing.yaml_data if existing is not None else default_profile_yaml()
    profile = await build_profile_from_text(
        db,
        yaml_text=yaml_text,
        cv_text=cv_text,
        user_id=current_user.id,
        profile_review_data=existing.profile_review_data if existing is not None else "{}",
        review_status=existing.review_status if existing is not None else "draft",
        reviewed_at=existing.reviewed_at if existing is not None else None,
    )
    await db.commit()
    await db.refresh(profile)
    return _profile_response(profile)
