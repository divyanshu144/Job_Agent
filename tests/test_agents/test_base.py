from __future__ import annotations

import json
import re

from backend.agents.base import BaseAgent
from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_unreplaced_slot(text: str) -> bool:
    """Return True if any {prior.field} placeholder survived injection."""
    return bool(re.search(r"\{prior\.\w+\}", text))


TEMPLATE = (
    "Profile: {profile}\n"
    "JD: {jd}\n"
    "Job parsed: {prior.job_parser}\n"
    "Match score: {prior.match_scorer}\n"
    "Gaps: {prior.gap_analyst}\n"
)

JP = JobParserOutput(
    required_skills=["Python"],
    nice_to_have=[],
    role_type="Engineer",
    seniority="Mid",
)
MS = MatchScorerOutput(
    score=75,
    matched_skills=["Python"],
    missing_skills=[],
    partial_matches=[],
)
GA = GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inject_replaces_none_prior_with_empty_string():
    """A None prior field must become "" — never the raw slot string."""
    prior = PriorOutputs()  # all fields None
    agent = BaseAgent.__new__(BaseAgent)
    result = agent._inject(TEMPLATE, "candidate", "job description", prior)

    assert not _has_unreplaced_slot(result), (
        "_inject() left a raw {prior.*} placeholder in the output"
    )
    # None fields must collapse to empty string, not the word "null"
    assert "job parsed: \n" in result.lower() or "job parsed: " in result.lower()


def test_inject_replaces_set_prior_with_json():
    """A set prior field must be replaced with its JSON serialisation."""
    prior = PriorOutputs(job_parser=JP, match_scorer=MS)
    agent = BaseAgent.__new__(BaseAgent)
    result = agent._inject(TEMPLATE, "candidate", "job description", prior)

    assert not _has_unreplaced_slot(result)
    assert json.dumps(JP.model_dump(), indent=2) in result
    assert json.dumps(MS.model_dump(), indent=2) in result


def test_inject_partial_prior_leaves_no_slots():
    """Mixed None / set prior: every slot is replaced, no raw placeholder survives."""
    prior = PriorOutputs(job_parser=JP)  # match_scorer and gap_analyst are None
    agent = BaseAgent.__new__(BaseAgent)
    result = agent._inject(TEMPLATE, "candidate", "job description", prior)

    assert not _has_unreplaced_slot(result)
    assert json.dumps(JP.model_dump(), indent=2) in result


def test_inject_profile_and_jd_always_replaced():
    """{profile} and {jd} slots are always substituted."""
    prior = PriorOutputs()
    agent = BaseAgent.__new__(BaseAgent)
    result = agent._inject(TEMPLATE, "Alice", "ML role", prior)

    assert "Profile: Alice" in result
    assert "JD: ML role" in result
