from __future__ import annotations

import logging
from typing import Callable

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.resume_editor import ResumeEditorAgent
from backend.config import settings
from backend.evals.faithfulness import validate_resume_faithfulness
from backend.models import Profile, ResumeDocument, ResumeEditRule
from backend.schemas import EditRuleCreate, EditRuleResponse, ResumeChatResult, ResumeEditorOutput
from backend.services import resume_document as docsvc
from backend.services.context_builder import build_resume_tailoring_context
from backend.services.profile_builder import get_owned_profile

logger = logging.getLogger(__name__)

# A persistent service failure escaping the agent's own transient retries is the
# design's "breaker-open" condition — the one place the scoped Sonnet fallback fires.
# APITimeoutError is a subclass of APIError; raw httpx.TimeoutException is NOT — BaseAgent's
# transient retryer matches both forms and reraises the original, so both must be caught here.
_SERVICE_FAILURES = (anthropic.APIError, httpx.TimeoutException)


async def _load_rules_text(db: AsyncSession, user_id: str) -> str:
    rows = (
        (
            await db.execute(
                select(ResumeEditRule).where(
                    ResumeEditRule.user_id == user_id,
                    ResumeEditRule.scope.in_(("resume", "both")),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ""
    return "\n".join(f"- {r.mode}: {r.text}" for r in rows)


async def _run_agent(
    db: AsyncSession,
    user_id: str,
    *,
    current_resume: str,
    profile_ctx: str,
    rules: str,
    instruction: str,
    agent_factory: Callable[[], ResumeEditorAgent],
) -> tuple[ResumeEditorOutput, bool]:
    """Run on Opus; on a persistent service failure fall back to Sonnet ONCE. Schema
    failures (AgentError) are NOT retried on the fallback — both models would fail the
    same way — they propagate for the caller to surface as edit_error.

    Returns (output, fallback_used) so the result can carry the design's subtle
    "applied with a backup model" note."""
    agent = agent_factory().with_tracking(db, user_id=user_id)
    agent.model = settings.resume_model
    try:
        return await agent.run(current_resume, profile_ctx, rules, instruction), False
    except _SERVICE_FAILURES:
        fallback = agent_factory().with_tracking(db, user_id=user_id)
        fallback.model = settings.resume_model_fallback
        return await fallback.run(current_resume, profile_ctx, rules, instruction), True


async def _capture_rule(
    db: AsyncSession, user_id: str, rule: EditRuleCreate
) -> EditRuleResponse | None:
    """Best-effort: the edit itself already committed; a rule-insert failure must never
    turn a successful edit into an error (the route would falsely report 'unchanged')."""
    try:
        row = ResumeEditRule(user_id=user_id, mode=rule.mode, text=rule.text, scope=rule.scope)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return EditRuleResponse(id=row.id, mode=row.mode, text=row.text, scope=row.scope)
    except Exception as exc:
        logger.warning("resume chat: rule capture failed (edit already committed): %s", exc)
        await db.rollback()
        return None


async def apply_chat_edit(
    db: AsyncSession,
    doc: ResumeDocument,
    user_id: str,
    base_rev: int,
    instruction: str,
    agent_factory: Callable[[], ResumeEditorAgent] = ResumeEditorAgent,
) -> ResumeChatResult:
    profile: Profile | None = await get_owned_profile(db, user_id)
    profile_ctx = build_resume_tailoring_context(profile)
    rules = await _load_rules_text(db, user_id)

    output, fallback_used = await _run_agent(
        db,
        user_id,
        current_resume=doc.content_json or "{}",
        profile_ctx=profile_ctx,
        rules=rules,
        instruction=instruction,
        agent_factory=agent_factory,
    )

    # Transactional: only commit if the agent output validated (it did — _call_structured).
    # apply_write raises StaleRevError on a stale base_rev without clobbering.
    doc = await docsvc.apply_write(
        db, doc, output.content, base_rev=base_rev, source="chat", summary=output.summary
    )
    # Capture before any later rollback: _capture_rule's failure path rolls back, which
    # expires ORM instances — a doc.rev access after that would sync-lazy-load (async unsafe).
    new_rev = doc.rev

    # Option (a): flag, never block. Computed against the same profile corpus the
    # agent was grounded on, AFTER the commit — a flagged edit is one undo away.
    warnings = validate_resume_faithfulness(output.content, profile_ctx)

    rule_resp: EditRuleResponse | None = None
    if output.new_rule is not None:
        rule_resp = await _capture_rule(db, user_id, output.new_rule)

    return ResumeChatResult(
        rev=new_rev,
        content=output.content,
        summary=output.summary,
        warnings=warnings,
        new_rule=rule_resp,
        fallback_used=fallback_used,
    )
