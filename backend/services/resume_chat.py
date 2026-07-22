from __future__ import annotations

from typing import Callable

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.resume_editor import ResumeEditorAgent
from backend.config import settings
from backend.models import Profile, ResumeDocument, ResumeEditRule
from backend.schemas import EditRuleResponse, ResumeChatResult, ResumeEditorOutput
from backend.services import resume_document as docsvc
from backend.services.context_builder import build_resume_tailoring_context
from backend.services.profile_builder import get_owned_profile

# A persistent service failure escaping the agent's own transient retries is the
# design's "breaker-open" condition — the one place the scoped Sonnet fallback fires.
_SERVICE_FAILURES = (anthropic.APIError, anthropic.APITimeoutError)


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
) -> ResumeEditorOutput:
    """Run on Opus; on a persistent service failure fall back to Sonnet ONCE. Schema
    failures (AgentError) are NOT retried on the fallback — both models would fail the
    same way — they propagate for the caller to surface as edit_error."""
    agent = agent_factory().with_tracking(db, user_id=user_id)
    agent.model = settings.resume_model
    try:
        return await agent.run(current_resume, profile_ctx, rules, instruction)
    except _SERVICE_FAILURES:
        fallback = agent_factory().with_tracking(db, user_id=user_id)
        fallback.model = settings.resume_model_fallback
        return await fallback.run(current_resume, profile_ctx, rules, instruction)


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

    output = await _run_agent(
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

    rule_resp: EditRuleResponse | None = None
    if output.new_rule is not None:
        row = ResumeEditRule(
            user_id=user_id,
            mode=output.new_rule.mode,
            text=output.new_rule.text,
            scope=output.new_rule.scope,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        rule_resp = EditRuleResponse(id=row.id, mode=row.mode, text=row.text, scope=row.scope)

    return ResumeChatResult(
        rev=doc.rev,
        content=output.content,
        summary=output.summary,
        warnings=[],  # Plan 3 populates faithfulness warnings here
        new_rule=rule_resp,
    )
