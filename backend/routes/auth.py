from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models import InviteToken, PasswordResetToken, User
from backend.schemas import (
    InviteCreate,
    InviteResponse,
    PasswordResetConfirm,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from backend.services.auth_service import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.services.rate_limit import limiter

router = APIRouter(tags=["auth"])

_INVITE_EXPIRE_HOURS = 72
_PASSWORD_RESET_EXPIRE_MINUTES = 30


@router.post("/auth/register", response_model=UserResponse)
@limiter.limit("10/minute", key_func=get_remote_address)  # per-IP; failures count
async def register(
    request: Request,
    data: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user_count: int = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    is_first_user = user_count == 0

    invite = None
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
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
    )
    return UserResponse.model_validate(user)


@router.post("/auth/login", response_model=UserResponse)
@limiter.limit("10/minute", key_func=get_remote_address)  # per-IP; failures count
async def login(
    request: Request,
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
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
    )
    return UserResponse.model_validate(user)


@router.post("/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("access_token", secure=settings.cookie_secure, samesite="lax")
    return {"ok": True}


@router.post("/auth/password-reset/request", response_model=PasswordResetRequestResponse)
@limiter.limit("5/minute", key_func=get_remote_address)
async def request_password_reset(
    request: Request,
    data: PasswordResetRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PasswordResetRequestResponse:
    user = (
        await db.execute(select(User).where(User.email == data.email.strip().lower()))
    ).scalar_one_or_none()
    reset_url: str | None = None
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                token=token,
                user_id=user.id,
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=_PASSWORD_RESET_EXPIRE_MINUTES),
            )
        )
        await db.commit()
        reset_url = f"/reset-password?token={token}"

    result = PasswordResetRequestResponse(
        ok=True,
        message="If the account exists, a password reset link has been created.",
    )
    if reset_url and not settings.is_production:
        result.reset_url = reset_url
    return result


@router.post("/auth/password-reset/confirm", response_model=PasswordResetConfirmResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def confirm_password_reset(
    request: Request,
    data: PasswordResetConfirm,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PasswordResetConfirmResponse:
    reset = (
        await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token == data.token)
            .where(PasswordResetToken.used_at.is_(None))
            .where(PasswordResetToken.expires_at > datetime.now(timezone.utc))
        )
    ).scalar_one_or_none()
    if reset is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = (await db.execute(select(User).where(User.id == reset.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(data.password)
    reset.used_at = datetime.now(timezone.utc)
    await db.commit()
    return PasswordResetConfirmResponse(ok=True)


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
