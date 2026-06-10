from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Protocol

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import SONNET
from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.database import SessionLocal
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResourcePlannerOutput,
)
from backend.services.instrumentation import new_trace_id, span
from backend.services.job_result import upsert_job_result
from backend.services.pipeline_errors import to_user_error
from backend.services.profile_builder import (
    build_compact_profile,
    get_or_build_profile,
    profile_content_hash,
)

logger = logging.getLogger(__name__)

# Canonical step order — the single source of truth for both phases.
PHASE1: list[str] = ["job_parser", "match_scorer", "gap_analyst"]
PHASE2: list[str] = ["resource_planner", "cover_letter", "resume_tailorer"]
ALL_STEPS: list[str] = PHASE1 + PHASE2
_PARALLEL_PHASE2 = ("cover_letter", "resume_tailorer")

_PRIOR_MODELS: dict[str, type[BaseModel]] = {
    "job_parser": JobParserOutput,
    "match_scorer": MatchScorerOutput,
    "gap_analyst": GapAnalystOutput,
    "resource_planner": ResourcePlannerOutput,
}

_AGENT_CLASSES: dict[str, type] = {
    "job_parser": JobParserAgent,
    "match_scorer": MatchScorerAgent,
    "gap_analyst": GapAnalystAgent,
    "resource_planner": ResourcePlannerAgent,
    "cover_letter": CoverLetterAgent,
    "resume_tailorer": ResumeTailorerAgent,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rebuild_prior(rows: list[JobResult]) -> PriorOutputs:
    """Reconstruct PriorOutputs from stored JobResult output rows (prefer outputs)."""
    prior = PriorOutputs()
    for row in rows:
        if not row.output_json:
            continue
        model = _PRIOR_MODELS.get(row.agent_name)
        if model is None:
            continue
        prior = prior.model_copy(
            update={row.agent_name: model.model_validate(json.loads(row.output_json))}
        )
    return prior


def analysis_cache_key(jd: str, profile: Profile) -> str:
    """Single derivation of the analysis cache key. Keyed on profile *content*
    (merged_profile), not profile.id — which rotates on every build. The one helper
    every cache site calls."""
    return hashlib.sha256(
        f"{jd}::{profile_content_hash(profile.merged_profile)}".encode()
    ).hexdigest()


@dataclass
class SSEEvent:
    name: str
    data: dict[str, Any]


@dataclass
class Phase1Result:
    analysis_id: str
    score: int
    partial: bool
    prior: PriorOutputs


class _AgentProtocol(Protocol):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> Any: ...


async def _run_phase1(
    jd: str,
    profile: Profile,
    db: AsyncSession,
    job_id: str | None = None,
    run_id: str | None = None,
    model: str = SONNET,
) -> Phase1Result:
    """Run job_parser → match_scorer → gap_analyst. Save Analysis + JobResult rows.

    No SSE. Called by discovery background task.
    job_id is set when called from discovery; None for manual-paste analyses.
    Pass model=HAIKU for bulk discovery to cut costs ~20x vs Sonnet.
    """
    # Return cached result if this exact JD+profile was already scored
    jd_hash = analysis_cache_key(jd, profile)
    cached = (
        await db.execute(
            select(Analysis).where(
                Analysis.jd_hash == jd_hash,
                Analysis.partial == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if cached is not None:
        from backend.services.instrumentation import log_cache_hit

        await log_cache_hit(db, "phase1_cache", model, run_id=run_id, analysis_id=cached.id)
        score_row = (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id == cached.id,
                    JobResult.agent_name == "match_scorer",
                )
            )
        ).scalar_one_or_none()
        score = (
            json.loads(score_row.output_json).get("score", 0)
            if score_row and score_row.output_json
            else 0
        )
        return Phase1Result(
            analysis_id=cached.id,
            score=score,
            partial=cached.partial,
            prior=PriorOutputs(),
        )

    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    # Create placeholder Analysis row BEFORE agents run so analysis_id is
    # available for LLM call tracking.
    analysis = Analysis(
        jd_text=jd,
        profile_id=profile.id,
        partial=True,
        evaluate_only=True,
        jd_hash=jd_hash,
        job_id=job_id,
    )
    db.add(analysis)
    await db.flush()

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1_agents: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    errors: dict[str, tuple[str, str]] = {}
    try:
        for agent_name, agent, profile_str in phase1_agents:
            agent.model = model  # type: ignore[attr-defined]
            agent.with_tracking(db, run_id=run_id, analysis_id=analysis.id)  # type: ignore[attr-defined]
            try:
                async with span(
                    db, kind="span", name=agent_name, analysis_id=analysis.id, run_id=run_id
                ):
                    output = await agent.run(profile_str, jd, prior)
                prior = prior.model_copy(update={agent_name: output})
                results[agent_name] = output.model_dump()
            except Exception as e:
                logger.exception("phase1 agent %s failed", agent_name)
                partial = True
                ue = to_user_error(agent_name, e)
                errors[agent_name] = (ue.message, ue.code)
    finally:
        analysis.partial = partial
        for name, data in results.items():
            await upsert_job_result(db, analysis.id, name, output_json=json.dumps(data))
        for name, (msg, code) in errors.items():
            await upsert_job_result(db, analysis.id, name, error=msg, error_code=code)
        await db.commit()

    score = results.get("match_scorer", {}).get("score", 0)
    return Phase1Result(
        analysis_id=analysis.id,
        score=score,
        partial=partial,
        prior=prior,
    )


async def run_evaluate_pipeline(
    jd: str, db: AsyncSession, user_id: str | None = None
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 1: job_parser → match_scorer → gap_analyst.

    job_parser and match_scorer receive a compact profile (YAML + CV excerpt).
    gap_analyst receives the full merged profile.
    Saves an Analysis row with evaluate_only=True.
    Returns cached result immediately if same JD+profile was already analysed.
    """
    new_trace_id()
    profile = await get_or_build_profile(db, user_id=user_id)
    jd_hash = analysis_cache_key(jd, profile)

    # Cache check: return immediately if a complete analysis already exists for this JD+profile
    cached = (
        await db.execute(
            select(Analysis).where(
                Analysis.jd_hash == jd_hash,
                Analysis.partial == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if cached is not None:
        from backend.services.instrumentation import log_cache_hit

        await log_cache_hit(db, "phase1_cache", SONNET, analysis_id=cached.id)
        score_row = (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id == cached.id,
                    JobResult.agent_name == "match_scorer",
                )
            )
        ).scalar_one_or_none()
        score = (
            json.loads(score_row.output_json).get("score", 0)
            if score_row and score_row.output_json
            else 0
        )
        yield SSEEvent(
            "pipeline_done",
            {
                "analysis_id": cached.id,
                "score": score,
                "partial": cached.partial,
                "evaluate_only": cached.evaluate_only,
            },
        )
        return

    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    # Create placeholder Analysis before agents so analysis_id is trackable
    analysis = Analysis(
        jd_text=jd,
        profile_id=profile.id,
        partial=True,
        evaluate_only=True,
        jd_hash=jd_hash,
        user_id=user_id,
    )
    db.add(analysis)
    await db.flush()

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    errors: dict[str, tuple[str, str]] = {}
    try:
        for agent_name, agent, profile_str in phase1:
            agent.with_tracking(db, analysis_id=analysis.id, user_id=user_id)  # type: ignore[attr-defined]
            yield SSEEvent("agent_start", {"agent": agent_name})
            try:
                async with span(db, kind="span", name=agent_name, analysis_id=analysis.id):
                    output = await agent.run(profile_str, jd, prior)
                prior = prior.model_copy(update={agent_name: output})
                results[agent_name] = output.model_dump()
                yield SSEEvent("agent_done", {"agent": agent_name, "output": output.model_dump()})
            except Exception as e:
                logger.exception("phase1 agent %s failed", agent_name)
                partial = True
                ue = to_user_error(agent_name, e)
                errors[agent_name] = (ue.message, ue.code)
                yield SSEEvent(
                    "pipeline_error",
                    {"agent": agent_name, "error": ue.message, "code": ue.code},
                )
    finally:
        analysis.partial = partial
        # Denormalize role/company/score onto the Analysis for the History list.
        jp_out = results.get("job_parser", {})
        analysis.role_type = jp_out.get("role_type")
        analysis.company = jp_out.get("company")
        analysis.match_score = results.get("match_scorer", {}).get("score")
        for name, output in results.items():
            await upsert_job_result(db, analysis.id, name, output_json=json.dumps(output))
        for name, (msg, code) in errors.items():
            await upsert_job_result(db, analysis.id, name, error=msg, error_code=code)
        await db.commit()

    score = results.get("match_scorer", {}).get("score", 0)
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis.id,
            "score": score,
            "partial": partial,
            "evaluate_only": True,
        },
    )


async def run_steps(
    analysis_id: str,
    agents: list[str],
    db: AsyncSession,
    user_id: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """Run a subset of pipeline steps against an EXISTING analysis, in place.

    The single runner for both phases. Rebuilds PriorOutputs from stored rows,
    runs the requested agents in canonical dependency order (Phase-1 sequential,
    then resource_planner, then cover_letter ∥ resume_tailorer), upserts each
    result, and recomputes denormalized fields / evaluate_only / partial /
    quality_signals from the full stored set. Never creates a second Analysis.
    """
    new_trace_id()
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (
        user_id is not None and analysis.user_id is not None and analysis.user_id != user_id
    ):
        yield SSEEvent(
            "pipeline_error", {"agent": "system", "error": f"Analysis {analysis_id} not found"}
        )
        yield SSEEvent(
            "pipeline_done",
            {"analysis_id": analysis_id, "score": 0, "partial": True, "evaluate_only": True},
        )
        return

    profile = (
        await db.execute(select(Profile).where(Profile.id == analysis.profile_id))
    ).scalar_one_or_none()
    full = profile.merged_profile if profile else ""
    compact = build_compact_profile(profile.yaml_data, profile.cv_text) if profile else ""
    profile_for = {
        "job_parser": compact,
        "match_scorer": compact,
        "gap_analyst": full,
        "resource_planner": full,
        "cover_letter": full,
        "resume_tailorer": full,
    }

    stored = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    prior = _rebuild_prior(list(stored))

    requested = [s for s in ALL_STEPS if s in set(agents)]
    yield SSEEvent("pipeline_start", {"total_agents": len(requested)})

    parallel = [s for s in _PARALLEL_PHASE2 if s in requested]
    sequential = [s for s in requested if s not in parallel]

    for name in sequential:
        agent = _AGENT_CLASSES[name]()
        agent.with_tracking(db, analysis_id=analysis.id, user_id=analysis.user_id)
        yield SSEEvent("agent_start", {"agent": name})
        try:
            async with span(db, kind="span", name=name, analysis_id=analysis.id):
                output = await agent.run(profile_for[name], analysis.jd_text, prior)
            prior = prior.model_copy(update={name: output})
            await upsert_job_result(
                db, analysis.id, name, output_json=json.dumps(output.model_dump())
            )
            yield SSEEvent("agent_done", {"agent": name, "output": output.model_dump()})
        except Exception as e:
            logger.exception("step %s failed", name)
            ue = to_user_error(name, e)
            await upsert_job_result(db, analysis.id, name, error=ue.message, error_code=ue.code)
            yield SSEEvent("pipeline_error", {"agent": name, "error": ue.message, "code": ue.code})

    if parallel:
        for name in parallel:
            yield SSEEvent("agent_start", {"agent": name})
        aid = analysis.id
        uid = analysis.user_id
        jd = analysis.jd_text
        snapshot = prior

        async def _tracked(name: str) -> Any:
            # Own session per coroutine — sharing the route session across
            # concurrent coroutines corrupts SQLAlchemy's unit-of-work state.
            async with SessionLocal() as own_db:
                agent = _AGENT_CLASSES[name]()
                agent.with_tracking(own_db, analysis_id=aid, user_id=uid)
                async with span(own_db, kind="span", name=name, analysis_id=aid):
                    return await agent.run(full, jd, snapshot)

        results = await asyncio.gather(*[_tracked(n) for n in parallel], return_exceptions=True)
        for name, result in zip(parallel, results):
            if isinstance(result, BaseException):
                # Never swallow shutdown signals — re-raise before the catch.
                if isinstance(result, (KeyboardInterrupt, SystemExit)):
                    raise result
                logger.error("step %s failed", name, exc_info=result)
                exc = result if isinstance(result, Exception) else Exception(str(result))
                ue = to_user_error(name, exc)
                await upsert_job_result(db, analysis.id, name, error=ue.message, error_code=ue.code)
                yield SSEEvent(
                    "pipeline_error", {"agent": name, "error": ue.message, "code": ue.code}
                )
            else:
                await upsert_job_result(
                    db, analysis.id, name, output_json=json.dumps(result.model_dump())
                )
                yield SSEEvent("agent_done", {"agent": name, "output": result.model_dump()})

    # Finalize from the full stored set (not just this run's results).
    final_rows = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    output_agents = {r.agent_name for r in final_rows if r.output_json}
    final_prior = _rebuild_prior(list(final_rows))
    if final_prior.job_parser is not None:
        analysis.role_type = final_prior.job_parser.role_type
        analysis.company = final_prior.job_parser.company
    if final_prior.match_scorer is not None:
        analysis.match_score = final_prior.match_scorer.score
    # evaluate_only is governed by Phase-2 completion ONLY (a Phase-1 retry never flips it).
    analysis.evaluate_only = not set(PHASE2) <= output_agents
    # partial is False only when every step across both phases has an output.
    analysis.partial = not set(ALL_STEPS) <= output_agents
    quality_signals = _build_quality_signals(final_prior)
    analysis.quality_signals = json.dumps(quality_signals)
    await db.commit()

    score = (
        final_prior.match_scorer.score if final_prior.match_scorer else (analysis.match_score or 0)
    )
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis_id,
            "score": score,
            "partial": analysis.partial,
            "evaluate_only": analysis.evaluate_only,
            "quality_signals": quality_signals,
        },
    )


async def run_generate_pipeline(
    analysis_id: str, db: AsyncSession, user_id: str | None = None
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 2 entry: run the missing Phase-2 steps for an analysis. Thin wrapper
    over run_steps (the single runner)."""
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (
        user_id is not None and analysis.user_id is not None and analysis.user_id != user_id
    ):
        yield SSEEvent(
            "pipeline_error", {"agent": "system", "error": f"Analysis {analysis_id} not found"}
        )
        return

    output_agents = await _output_agents(db, analysis_id)
    missing = [s for s in PHASE2 if s not in output_agents]
    if not missing:
        yield SSEEvent(
            "pipeline_error",
            {"agent": "system", "error": "Documents already generated for this analysis"},
        )
        return

    async for event in run_steps(analysis_id, missing, db, user_id):
        yield event


async def run_retry_pipeline(
    analysis_id: str,
    db: AsyncSession,
    *,
    agents: list[str] | None = None,
    scope: str = "failed",
    is_admin: bool = False,
    user_id: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """Re-run failed/missing steps (scope=failed) or all steps (scope=all, admin).

    Never re-runs a succeeded step unless scope=all. Claims a DB-level lock
    (Analysis.retry_running_at) so concurrent retries don't double-charge.
    """
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None or (
        user_id is not None and analysis.user_id is not None and analysis.user_id != user_id
    ):
        yield SSEEvent(
            "pipeline_error", {"agent": "system", "error": f"Analysis {analysis_id} not found"}
        )
        return

    output_agents = await _output_agents(db, analysis_id)
    named = set(agents) if agents else set(ALL_STEPS)
    if scope == "all" and is_admin:
        resolved = [s for s in ALL_STEPS if s in named]
    else:
        # failed/missing only — never re-run a succeeded step
        resolved = [s for s in ALL_STEPS if s in named and s not in output_agents]

    if not resolved:
        async for event in _nothing_to_retry(analysis):
            yield event
        return

    # Atomic claim: only one retry may hold retry_running_at at a time.
    claimed = (
        await db.execute(
            update(Analysis)
            .where(Analysis.id == analysis_id, Analysis.retry_running_at.is_(None))
            .values(retry_running_at=_utcnow())
            .returning(Analysis.id)
        )
    ).scalar_one_or_none()
    await db.commit()
    if claimed is None:
        yield SSEEvent(
            "pipeline_error",
            {"agent": "system", "error": "A retry is already in progress. Please wait."},
        )
        async for event in _nothing_to_retry(analysis):
            yield event
        return

    try:
        async for event in run_steps(analysis_id, resolved, db, user_id):
            yield event
    finally:
        await db.execute(
            update(Analysis).where(Analysis.id == analysis_id).values(retry_running_at=None)
        )
        await db.commit()


async def _output_agents(db: AsyncSession, analysis_id: str) -> set[str]:
    rows = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    return {r.agent_name for r in rows if r.output_json}


async def _nothing_to_retry(analysis: Analysis) -> AsyncGenerator[SSEEvent, None]:
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis.id,
            "score": analysis.match_score or 0,
            "partial": analysis.partial,
            "evaluate_only": analysis.evaluate_only,
        },
    )


def _build_quality_signals(prior: PriorOutputs) -> dict[str, Any]:
    """Per-run quality summary assembled at end of Phase 2 from prior outputs."""
    ms = prior.match_scorer
    ga = prior.gap_analyst
    rp = prior.resource_planner
    pm = rp.planner_meta if rp else None
    confidences = list(pm.gap_confidences.values()) if pm and pm.gap_confidences else []
    return {
        "match_score": ms.score if ms else None,
        # match_scorer is single-pass today; no second iteration to adjust against.
        "match_score_adjusted": None,
        "gaps_critical": len(ga.critical_gaps) if ga else 0,
        "gaps_nice_to_have": len(ga.nice_to_have_gaps) if ga else 0,
        "resource_confidence_avg": round(sum(confidences) / len(confidences), 3)
        if confidences
        else None,
        "low_confidence_gaps": list(pm.low_confidence_gaps) if pm else [],
    }
