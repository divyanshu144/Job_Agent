import json
from unittest.mock import patch

import pytest

from backend.schemas import (
    CoverLetterOutput,
    GapAnalystOutput,
    JobParserOutput,
    MatchScorerOutput,
    PriorOutputs,
)

PRIOR = PriorOutputs(
    job_parser=JobParserOutput(
        required_skills=["Python"], nice_to_have=[], role_type="ML Engineer", seniority="Senior"
    ),
    match_scorer=MatchScorerOutput(
        score=80, matched_skills=["Python"], missing_skills=[], partial_matches=[]
    ),
    gap_analyst=GapAnalystOutput(critical_gaps=[], nice_to_have_gaps=[]),
)
HAPPY = json.dumps(
    {
        "subject": "Cover Letter – ML Engineer",
        "body": "Dear Hiring Manager...",
        "tone_notes": "confident",
    }
)
# First entry: truncated JSON (JSONDecodeError);
# second: missing required fields body+tone_notes (ValidationError)
MALFORMED = [HAPPY[:10], json.dumps({"subject": "ok"})]


async def test_cover_letter_happy():
    from backend.agents.cover_letter import CoverLetterAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(CoverLetterAgent, "_call", new=_call):
        result = await CoverLetterAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, CoverLetterOutput)
    assert "ML Engineer" in result.subject


@pytest.mark.parametrize("bad", MALFORMED)
async def test_cover_letter_malformed(bad):
    from backend.agents.cover_letter import CoverLetterAgent
    from backend.agents.job_parser import AgentError

    async def _call(self, s, u):
        return bad

    with patch.object(CoverLetterAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await CoverLetterAgent().run("profile", "jd " * 15, PRIOR)
