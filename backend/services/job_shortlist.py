from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Analysis, Job, JobResult
from backend.schemas import JobShortlistItem


@dataclass(frozen=True)
class _ShortlistRow:
    job: Job
    analysis_id: str | None


def recommended_action(score: int) -> Literal["apply", "maybe", "skip"]:
    if score >= 75:
        return "apply"
    if score >= 55:
        return "maybe"
    return "skip"


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_source(job: Job) -> str:
    try:
        sources = json.loads(job.sources or "[]")
    except json.JSONDecodeError:
        sources = []
    if isinstance(sources, list) and sources:
        return str(sources[0])
    return ""


def _top_match_reasons(match_data: dict[str, Any], limit: int = 3) -> list[str]:
    reasons: list[str] = []
    for key in ("matched_skills", "partial_matches"):
        value = match_data.get(key)
        if isinstance(value, list):
            reasons.extend(str(item) for item in value if item)
    return reasons[:limit]


def _top_gaps(match_data: dict[str, Any], gap_data: dict[str, Any], limit: int = 3) -> list[str]:
    gaps: list[str] = []
    critical = gap_data.get("critical_gaps")
    if isinstance(critical, list):
        for item in critical:
            if isinstance(item, dict) and item.get("skill"):
                gaps.append(str(item["skill"]))
            elif item:
                gaps.append(str(item))
    missing = match_data.get("missing_skills")
    if isinstance(missing, list):
        gaps.extend(str(item) for item in missing if item)
    deduped = list(dict.fromkeys(gaps))
    return deduped[:limit]


async def _result_data_by_analysis(
    db: AsyncSession, analysis_ids: list[str]
) -> dict[str, dict[str, dict[str, Any]]]:
    if not analysis_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(JobResult).where(
                    JobResult.analysis_id.in_(analysis_ids),
                    JobResult.agent_name.in_(["match_scorer", "gap_analyst"]),
                )
            )
        )
        .scalars()
        .all()
    )
    data: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        data.setdefault(row.analysis_id, {})[row.agent_name] = _json_dict(row.output_json)
    return data


async def get_job_shortlist(db: AsyncSession, limit: int = 10) -> list[JobShortlistItem]:
    latest_analysis_id = (
        select(Analysis.id)
        .where(Analysis.job_id == Job.id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(1)
        .correlate(Job)
        .scalar_subquery()
    )
    query = (
        select(Job, latest_analysis_id.label("analysis_id"))
        .where(Job.state == "scored")
        .where(Job.relevance_score.is_not(None))
    )
    if not settings.enable_workatastartup_source:
        query = query.where(~Job.sources.like('%"workatastartup"%'))
    rows = (await db.execute(query.order_by(Job.relevance_score.desc()).limit(limit))).all()
    shortlist_rows = [_ShortlistRow(job=row.Job, analysis_id=row.analysis_id) for row in rows]
    result_data = await _result_data_by_analysis(
        db, [row.analysis_id for row in shortlist_rows if row.analysis_id is not None]
    )

    items: list[JobShortlistItem] = []
    for row in shortlist_rows:
        score = row.job.relevance_score or 0
        per_analysis = result_data.get(row.analysis_id or "", {})
        match_data = per_analysis.get("match_scorer", {})
        gap_data = per_analysis.get("gap_analyst", {})
        items.append(
            JobShortlistItem(
                id=row.job.id,
                title=row.job.title,
                company=row.job.company,
                location=row.job.location,
                source=_first_source(row.job),
                source_url=row.job.source_url,
                score=score,
                top_match_reasons=_top_match_reasons(match_data),
                top_gaps=_top_gaps(match_data, gap_data),
                recommended_action=recommended_action(score),
            )
        )
    return items
