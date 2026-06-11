from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User, UserTargetCompany
from backend.schemas import (
    TargetCompanyCreate,
    TargetCompanyResponse,
    TargetCompanyUpdate,
)
from backend.services.auth_service import get_current_user

# Regular-tier: any authenticated user manages their OWN target list. NOT admin.
router = APIRouter(tags=["targets"])


@router.get("/targets", response_model=list[TargetCompanyResponse])
async def list_targets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TargetCompanyResponse]:
    rows = (
        (
            await db.execute(
                select(UserTargetCompany)
                .where(UserTargetCompany.user_id == current_user.id)
                .order_by(UserTargetCompany.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [TargetCompanyResponse.model_validate(r) for r in rows]


@router.post("/targets", response_model=TargetCompanyResponse)
async def add_target(
    data: TargetCompanyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TargetCompanyResponse:
    existing = (
        await db.execute(
            select(UserTargetCompany).where(
                UserTargetCompany.user_id == current_user.id,
                UserTargetCompany.ats == data.ats,
                UserTargetCompany.slug == data.slug,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="That company is already in your target list")
    row = UserTargetCompany(user_id=current_user.id, name=data.name, ats=data.ats, slug=data.slug)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return TargetCompanyResponse.model_validate(row)


async def _owned(db: AsyncSession, target_id: str, user_id: str) -> UserTargetCompany:
    row = (
        await db.execute(
            select(UserTargetCompany).where(
                UserTargetCompany.id == target_id,
                UserTargetCompany.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return row


@router.patch("/targets/{target_id}", response_model=TargetCompanyResponse)
async def update_target(
    target_id: str,
    data: TargetCompanyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TargetCompanyResponse:
    row = await _owned(db, target_id, current_user.id)
    row.active = data.active
    await db.commit()
    await db.refresh(row)
    return TargetCompanyResponse.model_validate(row)


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(
    target_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await _owned(db, target_id, current_user.id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
