from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.base import SONNET
from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import AgentError, JobParserAgent
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
)
from backend.services.instrumentation import new_trace_id, span
from backend.services.profile_builder import build_compact_profile, get_or_build_profile


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
    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()
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

    errors: dict[str, str] = {}
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
            except AgentError as e:
                partial = True
                errors[agent_name] = str(e)
    finally:
        analysis.partial = partial
        for name, data in results.items():
            db.add(
                JobResult(
                    analysis_id=analysis.id,
                    agent_name=name,
                    output_json=json.dumps(data),
                )
            )
        for name, err in errors.items():
            db.add(JobResult(analysis_id=analysis.id, agent_name=name, error=err))
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
    jd_hash = hashlib.sha256(f"{jd}::{profile.id}".encode()).hexdigest()

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

    errors: dict[str, str] = {}
    try:
        for agent_name, agent, profile_str in phase1:
            agent.with_tracking(db, analysis_id=analysis.id)  # type: ignore[attr-defined]
            yield SSEEvent("agent_start", {"agent": agent_name})
            try:
                async with span(db, kind="span", name=agent_name, analysis_id=analysis.id):
                    output = await agent.run(profile_str, jd, prior)
                prior = prior.model_copy(update={agent_name: output})
                results[agent_name] = output.model_dump()
                yield SSEEvent("agent_done", {"agent": agent_name, "output": output.model_dump()})
            except AgentError as e:
                partial = True
                errors[agent_name] = str(e)
                yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(e)})
    finally:
        analysis.partial = partial
        # Denormalize role/company/score onto the Analysis for the History list.
        jp_out = results.get("job_parser", {})
        analysis.role_type = jp_out.get("role_type")
        analysis.company = jp_out.get("company")
        analysis.match_score = results.get("match_scorer", {}).get("score")
        for name, output in results.items():
            db.add(
                JobResult(
                    analysis_id=analysis.id,
                    agent_name=name,
                    output_json=json.dumps(output),
                )
            )
        for name, err in errors.items():
            db.add(JobResult(analysis_id=analysis.id, agent_name=name, error=err))
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


async def run_generate_pipeline(
    analysis_id: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 2: resource_planner → [cover_letter ∥ resume_tailorer].

    Loads Phase 1 results from DB to rebuild PriorOutputs.
    Appends Phase 2 JobResult rows and sets evaluate_only=False on the Analysis.
    """
    new_trace_id()
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if analysis is None:
        yield SSEEvent(
            "pipeline_error", {"agent": "system", "error": f"Analysis {analysis_id} not found"}
        )
        return
    if not analysis.evaluate_only:
        yield SSEEvent(
            "pipeline_error",
            {"agent": "system", "error": "Documents already generated for this analysis"},
        )
        return

    profile = (
        await db.execute(select(Profile).where(Profile.id == analysis.profile_id))
    ).scalar_one_or_none()
    full = profile.merged_profile if profile else ""

    # Rebuild PriorOutputs from stored Phase 1 results
    stored = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    prior = PriorOutputs()
    for row in stored:
        if not row.output_json:
            continue
        data = json.loads(row.output_json)
        if row.agent_name == "job_parser":
            prior = prior.model_copy(update={"job_parser": JobParserOutput.model_validate(data)})
        elif row.agent_name == "match_scorer":
            prior = prior.model_copy(
                update={"match_scorer": MatchScorerOutput.model_validate(data)}
            )
        elif row.agent_name == "gap_analyst":
            prior = prior.model_copy(update={"gap_analyst": GapAnalystOutput.model_validate(data)})

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    partial = False

    # resource_planner runs first (gap_analyst output feeds into it)
    rp_agent = ResourcePlannerAgent()
    rp_agent.with_tracking(db, analysis_id=analysis.id)
    yield SSEEvent("agent_start", {"agent": "resource_planner"})
    try:
        async with span(db, kind="span", name="resource_planner", analysis_id=analysis.id):
            rp_output = await rp_agent.run(full, analysis.jd_text, prior)
        prior = prior.model_copy(update={"resource_planner": rp_output})
        results["resource_planner"] = rp_output.model_dump()
        yield SSEEvent(
            "agent_done", {"agent": "resource_planner", "output": rp_output.model_dump()}
        )
    except AgentError as e:
        partial = True
        errors["resource_planner"] = str(e)
        yield SSEEvent("pipeline_error", {"agent": "resource_planner", "error": str(e)})

    # cover_letter + resume_tailorer run in parallel
    yield SSEEvent("agent_start", {"agent": "cover_letter"})
    yield SSEEvent("agent_start", {"agent": "resume_tailorer"})

    # Each parallel agent gets its own session — sharing the route session across
    # concurrent coroutines corrupts SQLAlchemy's unit-of-work state.
    aid = analysis.id

    async def _tracked(
        name: str, AgentClass: type, profile_str: str, jd: str, p: PriorOutputs
    ) -> Any:
        async with SessionLocal() as own_db:
            agent = AgentClass()
            agent.with_tracking(own_db, analysis_id=aid)
            async with span(own_db, kind="span", name=name, analysis_id=aid):
                return await agent.run(profile_str, jd, p)

    cl_result: Any
    rt_result: Any
    cl_result, rt_result = await asyncio.gather(
        _tracked("cover_letter", CoverLetterAgent, full, analysis.jd_text, prior),
        _tracked("resume_tailorer", ResumeTailorerAgent, full, analysis.jd_text, prior),
        return_exceptions=True,
    )

    for agent_name, result in [("cover_letter", cl_result), ("resume_tailorer", rt_result)]:
        if isinstance(result, BaseException):
            partial = True
            errors[agent_name] = str(result)
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(result)})
        else:
            results[agent_name] = result.model_dump()
            yield SSEEvent("agent_done", {"agent": agent_name, "output": result.model_dump()})

    # Persist Phase 2 results and mark analysis complete
    for name, output in results.items():
        db.add(
            JobResult(
                analysis_id=analysis_id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    for name, err in errors.items():
        db.add(JobResult(analysis_id=analysis_id, agent_name=name, error=err))
    analysis.evaluate_only = False
    if partial:
        analysis.partial = True
    quality_signals = _build_quality_signals(prior)
    analysis.quality_signals = json.dumps(quality_signals)
    await db.commit()

    score = prior.match_scorer.score if prior.match_scorer else 0
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis_id,
            "score": score,
            "partial": partial or analysis.partial,
            "evaluate_only": False,
            "quality_signals": quality_signals,
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
