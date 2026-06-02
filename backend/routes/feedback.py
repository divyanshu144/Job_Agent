from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Feedback, User
from backend.schemas import FeedbackCreate, FeedbackResponse
from backend.services.auth_service import get_current_user
from backend.services.instrumentation import get_trace_id

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Feedback:
    # EVALS HOOK: this row is the input a future backend/evals/ scorer consumes —
    # aggregate ratings per agent + correlate with PipelineEvent spans/failures to
    # produce quality scores (see backend/evals/__init__.py).
    row = Feedback(
        analysis_id=payload.analysis_id,
        agent_name=payload.agent_name,
        rating=payload.rating,
        note=payload.note,
        trace_id=get_trace_id(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/feedback", response_model=list[FeedbackResponse])
async def list_feedback(
    analysis_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Feedback]:
    q = select(Feedback).order_by(Feedback.created_at.desc())
    if analysis_id is not None:
        q = q.where(Feedback.analysis_id == analysis_id)
    return list((await db.execute(q)).scalars().all())
