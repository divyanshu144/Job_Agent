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
    return _pwd_context.hash(password)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)  # type: ignore[no-any-return]


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.jwt_secret, algorithm=_ALGORITHM)  # type: ignore[no-any-return]


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


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
