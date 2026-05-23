import json
from unittest.mock import patch

import pytest

from backend.schemas import JobParserOutput, PriorOutputs

FIXTURE_JD = (
    "We are looking for a Senior ML Engineer with 5+ years experience in Python, PyTorch,"
    " and deploying models to AWS. Nice to have: Kubernetes, Spark."
)

HAPPY_RESPONSE = json.dumps(
    {
        "required_skills": ["Python", "PyTorch", "AWS"],
        "nice_to_have": ["Kubernetes", "Spark"],
        "years_experience": 5,
        "role_type": "ML Engineer",
        "seniority": "Senior",
    }
)

MALFORMED_RESPONSES = [
    "Here is the analysis without any JSON object at all.",  # no JSON found
    HAPPY_RESPONSE[:40],  # truncated / invalid JSON
    json.dumps({"required_skills": "not-a-list"}),  # type mismatch
]


@pytest.fixture
def mock_call():
    async def _call(self, system, user):
        return HAPPY_RESPONSE

    return _call


async def test_job_parser_happy_path(mock_call):
    from backend.agents.job_parser import JobParserAgent

    with patch.object(JobParserAgent, "_call", new=mock_call):
        agent = JobParserAgent()
        result = await agent.run("profile text", FIXTURE_JD, PriorOutputs())
    assert isinstance(result, JobParserOutput)
    assert "Python" in result.required_skills
    assert result.seniority == "Senior"


@pytest.mark.parametrize("bad_response", MALFORMED_RESPONSES)
async def test_job_parser_malformed_raises(bad_response):
    from backend.agents.job_parser import AgentError, JobParserAgent

    async def _bad_call(self, system, user):
        return bad_response

    with patch.object(JobParserAgent, "_call", new=_bad_call):
        agent = JobParserAgent()
        with pytest.raises(AgentError):
            await agent.run("profile text", FIXTURE_JD, PriorOutputs())
