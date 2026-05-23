from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import AgentError, JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.models import Analysis, JobResult, Profile
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)
from backend.services.profile_builder import build_compact_profile, get_or_build_profile


@dataclass
class SSEEvent:
    name: str
    data: dict[str, Any]


class _AgentProtocol(Protocol):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> Any: ...


async def run_evaluate_pipeline(
    jd: str, db: AsyncSession
) -> AsyncGenerator[SSEEvent, None]:
    """Phase 1: job_parser → match_scorer → gap_analyst.

    job_parser and match_scorer receive a compact profile (YAML + CV excerpt).
    gap_analyst receives the full merged profile.
    Saves an Analysis row with evaluate_only=True.
    """
    profile = await get_or_build_profile(db)
    compact = build_compact_profile(profile.yaml_data, profile.cv_text)
    full = profile.merged_profile

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    results: dict[str, dict[str, Any]] = {}
    partial = False
    prior = PriorOutputs()

    phase1: list[tuple[str, _AgentProtocol, str]] = [
        ("job_parser", JobParserAgent(), compact),
        ("match_scorer", MatchScorerAgent(), compact),
        ("gap_analyst", GapAnalystAgent(), full),
    ]

    for agent_name, agent, profile_str in phase1:
        yield SSEEvent("agent_start", {"agent": agent_name})
        try:
            output = await agent.run(profile_str, jd, prior)
            prior = prior.model_copy(update={agent_name: output})
            results[agent_name] = output.model_dump()
            yield SSEEvent("agent_done", {"agent": agent_name, "output": output.model_dump()})
        except AgentError as e:
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(e)})

    score = results.get("match_scorer", {}).get("score", 0)
    analysis = Analysis(
        jd_text=jd, profile_id=profile.id, partial=partial, evaluate_only=True
    )
    db.add(analysis)
    await db.flush()

    for name, output in results.items():
        db.add(
            JobResult(
                analysis_id=analysis.id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    await db.commit()

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
        await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id))
    ).scalars().all()
    prior = PriorOutputs()
    for row in stored:
        if not row.output_json:
            continue
        data = json.loads(row.output_json)
        if row.agent_name == "job_parser":
            prior = prior.model_copy(
                update={"job_parser": JobParserOutput.model_validate(data)}
            )
        elif row.agent_name == "match_scorer":
            prior = prior.model_copy(
                update={"match_scorer": MatchScorerOutput.model_validate(data)}
            )
        elif row.agent_name == "gap_analyst":
            prior = prior.model_copy(
                update={"gap_analyst": GapAnalystOutput.model_validate(data)}
            )

    yield SSEEvent("pipeline_start", {"total_agents": 3})

    results: dict[str, dict[str, Any]] = {}
    partial = False

    # resource_planner runs first (gap_analyst output feeds into it)
    yield SSEEvent("agent_start", {"agent": "resource_planner"})
    try:
        rp_output = await ResourcePlannerAgent().run(full, analysis.jd_text, prior)
        prior = prior.model_copy(update={"resource_planner": rp_output})
        results["resource_planner"] = rp_output.model_dump()
        yield SSEEvent(
            "agent_done", {"agent": "resource_planner", "output": rp_output.model_dump()}
        )
    except AgentError as e:
        partial = True
        yield SSEEvent("pipeline_error", {"agent": "resource_planner", "error": str(e)})

    # cover_letter + resume_tailorer run in parallel
    yield SSEEvent("agent_start", {"agent": "cover_letter"})
    yield SSEEvent("agent_start", {"agent": "resume_tailorer"})

    cl_result, rt_result = await asyncio.gather(
        CoverLetterAgent().run(full, analysis.jd_text, prior),
        ResumeTailorerAgent().run(full, analysis.jd_text, prior),
        return_exceptions=True,
    )

    for agent_name, result in [("cover_letter", cl_result), ("resume_tailorer", rt_result)]:
        if isinstance(result, BaseException):
            partial = True
            yield SSEEvent("pipeline_error", {"agent": agent_name, "error": str(result)})
        else:
            results[agent_name] = result.model_dump()
            yield SSEEvent(
                "agent_done", {"agent": agent_name, "output": result.model_dump()}
            )

    # Persist Phase 2 results and mark analysis complete
    for name, output in results.items():
        db.add(
            JobResult(
                analysis_id=analysis_id,
                agent_name=name,
                output_json=json.dumps(output),
            )
        )
    analysis.evaluate_only = False
    if partial:
        analysis.partial = True
    await db.commit()

    score = prior.match_scorer.score if prior.match_scorer else 0
    yield SSEEvent(
        "pipeline_done",
        {
            "analysis_id": analysis_id,
            "score": score,
            "partial": partial or analysis.partial,
            "evaluate_only": False,
        },
    )
