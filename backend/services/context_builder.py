from __future__ import annotations

import json
import hashlib
import re
from typing import Any

from backend.models import Profile
from backend.schemas import PriorOutputs
from backend.services.profile_builder import build_compact_profile
from backend.services.profile_builder import profile_content_hash


class ContextPrerequisiteError(ValueError):
    """Raised when an agent is requested before its required prior outputs exist."""


REQUIRED_PRIORS: dict[str, tuple[str, ...]] = {
    "job_parser": (),
    "match_scorer": ("job_parser",),
    "gap_analyst": ("job_parser", "match_scorer"),
    "resource_planner": ("gap_analyst",),
    "cover_letter": ("job_parser", "match_scorer", "gap_analyst"),
    "resume_tailorer": ("job_parser", "match_scorer", "gap_analyst"),
}

FULL_PROFILE_AGENTS = {
    "gap_analyst",
    "resource_planner",
    "cover_letter",
    "resume_tailorer",
}

AGENT_CONTEXT_MODE: dict[str, str] = {
    "job_parser": "compact_profile",
    "match_scorer": "compact_profile",
    "gap_analyst": "retrieved_profile",
    "resource_planner": "retrieved_profile",
    "cover_letter": "retrieved_profile",
    "resume_tailorer": "retrieved_profile",
    "cold_email": "retrieved_profile",
}


def normalize_job_description(jd: str) -> str:
    """Normalize JD text for cache identity without changing the stored/prompted text."""
    return " ".join(jd.split())


def profile_context_for_agent(profile: Profile | None, agent_name: str) -> str:
    if profile is None:
        return ""
    if agent_name in FULL_PROFILE_AGENTS:
        return profile.merged_profile
    return build_compact_profile(profile.yaml_data, profile.cv_text)


def build_context_manifest(
    *,
    agent_name: str,
    profile: Profile | None,
    jd: str,
    prior: PriorOutputs,
) -> dict[str, Any]:
    included_priors = sorted(prior.model_dump(exclude_none=True).keys())
    profile_hash = profile_content_hash(profile.merged_profile) if profile else None
    return {
        "agent": agent_name,
        "profile_id": profile.id if profile else None,
        "profile_hash": profile_hash,
        "profile_context": AGENT_CONTEXT_MODE.get(agent_name, "unknown"),
        "jd_hash": hashlib.sha256(normalize_job_description(jd).encode()).hexdigest(),
        "jd_chars": len(jd),
        "required_priors": list(REQUIRED_PRIORS.get(agent_name, ())),
        "included_priors": included_priors,
        "missing_priors": missing_required_priors(agent_name, prior),
    }


def retrieval_query_for_agent(agent_name: str, jd: str, prior: PriorOutputs) -> str:
    pieces = [jd]
    if prior.job_parser is not None:
        pieces.extend(prior.job_parser.required_skills)
        pieces.extend(prior.job_parser.nice_to_have)
        pieces.append(prior.job_parser.role_type)
        pieces.append(prior.job_parser.seniority)
        if prior.job_parser.company:
            pieces.append(prior.job_parser.company)
    if prior.match_scorer is not None:
        pieces.extend(prior.match_scorer.matched_skills)
        pieces.extend(prior.match_scorer.partial_matches)
        pieces.extend(prior.match_scorer.missing_skills)
    if prior.gap_analyst is not None:
        pieces.extend(gap.skill for gap in prior.gap_analyst.critical_gaps)
        pieces.extend(gap.skill for gap in prior.gap_analyst.nice_to_have_gaps)
    if agent_name == "cover_letter":
        pieces.append("strongest matching evidence projects experience achievements")
    elif agent_name == "resume_tailorer":
        pieces.append("resume bullets skills projects experience education")
    elif agent_name == "resource_planner":
        pieces.append("skill gaps learning plan missing skills")
    return "\n".join(piece for piece in pieces if piece)


def build_outreach_profile_context(profile: Profile | None) -> str:
    """Compact profile context for outreach drafts."""
    if profile is None:
        return ""
    return build_compact_profile(profile.yaml_data, profile.cv_text)


def missing_required_priors(agent_name: str, prior: PriorOutputs) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_PRIORS.get(agent_name, ()):
        if getattr(prior, field, None) is None:
            missing.append(field)
    return missing


def validate_required_priors(agent_name: str, prior: PriorOutputs) -> None:
    missing = missing_required_priors(agent_name, prior)
    if missing:
        raise ContextPrerequisiteError(
            f"{agent_name} is missing required prior output(s): {', '.join(missing)}"
        )


def estimate_context_chars(system: Any, messages: Any) -> int:
    """Best-effort context-size estimate for observability logs."""
    return len(_to_text(system)) + len(_to_text(messages))


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        return str(value)


_UNRESOLVED_PRIOR_RE = re.compile(r"\{prior\.[a-zA-Z0-9_]+\}")


def find_unresolved_prior_placeholders(text: str) -> list[str]:
    return sorted(set(_UNRESOLVED_PRIOR_RE.findall(text)))
