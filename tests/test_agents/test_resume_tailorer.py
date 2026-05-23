import json
from unittest.mock import patch

import pytest

from backend.schemas import (
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
    ResumeTailorerOutput,
)

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Mid"
    ),
    match_scorer=MatchScorerOutput(
        score=72, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    ),
    gap_analyst=GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[]),
)
HAPPY = json.dumps(
    {
        "tailored_bullets": [
            {
                "original": "Built ML pipeline",
                "rewritten": "Engineered end-to-end ML pipeline with Python",
                "rationale": "adds JD keyword",
            }
        ]
    }
)
MALFORMED = [HAPPY[:10], json.dumps({"tailored_bullets": "not-a-list"})]


async def test_resume_tailorer_happy():
    from backend.agents.resume_tailorer import ResumeTailorerAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        result = await ResumeTailorerAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, ResumeTailorerOutput)
    assert result.tailored_bullets[0].original == "Built ML pipeline"


@pytest.mark.parametrize("bad", MALFORMED)
async def test_resume_tailorer_malformed(bad):
    from backend.agents.job_parser import AgentError
    from backend.agents.resume_tailorer import ResumeTailorerAgent

    async def _call(self, s, u):
        return bad

    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ResumeTailorerAgent().run("profile", "jd " * 15, PRIOR)
