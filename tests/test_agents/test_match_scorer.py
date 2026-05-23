import json
from unittest.mock import patch

import pytest

from backend.schemas import JobParserOutput, MatchScorerOutput, PriorOutputs

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(
        required_skills=["Python", "PyTorch"],
        nice_to_have=[],
        role_type="ML Engineer",
        seniority="Senior",
    )
)
HAPPY = json.dumps(
    {
        "score": 78,
        "matched_skills": ["Python"],
        "missing_skills": ["PyTorch"],
        "partial_matches": [],
    }
)
MALFORMED = [HAPPY[:20], json.dumps({"score": "high"}), "No JSON here"]


async def test_match_scorer_happy_path():
    from backend.agents.match_scorer import MatchScorerAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(MatchScorerAgent, "_call", new=_call):
        result = await MatchScorerAgent().run("profile", "jd text " * 10, PRIOR)
    assert isinstance(result, MatchScorerOutput)
    assert 0 <= result.score <= 100


@pytest.mark.parametrize("bad", MALFORMED)
async def test_match_scorer_malformed(bad):
    from backend.agents.match_scorer import AgentError, MatchScorerAgent

    async def _call(self, s, u):
        return bad

    with patch.object(MatchScorerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await MatchScorerAgent().run("profile", "jd text " * 10, PRIOR)
