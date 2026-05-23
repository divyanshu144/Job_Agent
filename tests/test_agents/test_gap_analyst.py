import json
from unittest.mock import patch

import pytest

from backend.schemas import GapAnalystOutput, JobParserOutput, MatchScorerOutput, PriorOutputs

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(
        required_skills=["Kubernetes"], nice_to_have=[], role_type="DevOps", seniority="Mid"
    ),
    match_scorer=MatchScorerOutput(
        score=55, matched_skills=[], missing_skills=["Kubernetes"], partial_matches=[]
    ),
)
HAPPY = json.dumps(
    {
        "critical_gaps": [
            {"skill": "Kubernetes", "impact": "core requirement", "rationale": "listed as required"}
        ],
        "nice_to_have_gaps": [],
    }
)
MALFORMED = [HAPPY[:15], json.dumps({"critical_gaps": "not-a-list"})]


async def test_gap_analyst_happy_path():
    from backend.agents.gap_analyst import GapAnalystAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(GapAnalystAgent, "_call", new=_call):
        result = await GapAnalystAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, GapAnalystOutput)
    assert result.critical_gaps[0].skill == "Kubernetes"


@pytest.mark.parametrize("bad", MALFORMED)
async def test_gap_analyst_malformed(bad):
    from backend.agents.gap_analyst import GapAnalystAgent
    from backend.agents.job_parser import AgentError

    async def _call(self, s, u):
        return bad

    with patch.object(GapAnalystAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await GapAnalystAgent().run("profile", "jd " * 15, PRIOR)
