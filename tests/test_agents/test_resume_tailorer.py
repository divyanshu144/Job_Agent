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
        "headline": "ML Engineer",
        "summary": "Builds Python ML systems.",
        "skills": ["Python"],
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "dates": "2022-2024",
                "bullets": ["Built ML pipeline with Python"],
            }
        ],
        "projects": [],
        "education": [],
        "tailored_bullets": [
            {
                "original": "Built ML pipeline",
                "rewritten": "Engineered end-to-end ML pipeline with Python",
                "rationale": "adds JD keyword",
            }
        ],
    }
)
MALFORMED = [HAPPY[:10], json.dumps({"tailored_bullets": "not-a-list"})]


async def test_resume_tailorer_happy():
    from backend.agents.resume_tailorer import ResumeTailorerAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        result = await ResumeTailorerAgent().run(
            "## CV Text\nAcme Engineer. Built ML pipeline with Python.", "jd " * 15, PRIOR
        )
    assert isinstance(result, ResumeTailorerOutput)
    assert result.headline == "ML Engineer"
    assert result.skills == ["Python"]
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


def test_prompt_demonstrates_omitted_items_element_shape():
    """Regression: an empty `"omitted_items": []` in the prompt left the model to
    guess the shape (it emitted strings → OmittedItem ValidationError → repeated
    retry failures). The example must show the {field, value, reason} object."""
    from backend.agents.base import PROMPTS_DIR

    text = (PROMPTS_DIR / "resume_tailorer.md").read_text()
    schema_text = text[text.index("## Output Schema") :]
    schema = json.loads(schema_text[schema_text.index("{") : schema_text.rindex("}") + 1])

    assert schema["omitted_items"], "omitted_items must demonstrate its element shape, not be []"
    assert set(schema["omitted_items"][0]) == {"field", "value", "reason"}


async def test_resume_tailorer_accepts_omitted_items_objects():
    from backend.agents.resume_tailorer import ResumeTailorerAgent

    payload = json.loads(HAPPY)
    payload["omitted_items"] = [
        {"field": "skills", "value": "Kubernetes", "reason": "not present in CV text"}
    ]

    async def _call(self, s, u):
        return json.dumps(payload)

    with patch.object(ResumeTailorerAgent, "_call", new=_call):
        result = await ResumeTailorerAgent().run(
            "## CV Text\nAcme Engineer. Built ML pipeline with Python.", "jd " * 15, PRIOR
        )
    assert result.omitted_items[0].field == "skills"
    assert result.omitted_items[0].reason == "not present in CV text"


async def test_resume_tailorer_self_corrects_omitted_items_strings():
    """The exact production failure: the model emits omitted_items as plain
    strings (invalid against OmittedItem). _call_structured feeds the error back
    and the second attempt returns valid objects — self-healed in one extra call."""
    from unittest.mock import AsyncMock

    from backend.agents.resume_tailorer import ResumeTailorerAgent

    bad = json.loads(HAPPY)
    bad["omitted_items"] = ["All experience omitted to avoid fabrication."]  # wrong shape
    good = json.loads(HAPPY)
    good["omitted_items"] = [{"field": "skills", "value": "K8s", "reason": "absent from CV"}]

    mock = AsyncMock(side_effect=[json.dumps(bad), json.dumps(good)])
    with patch.object(ResumeTailorerAgent, "_call", new=mock):
        result = await ResumeTailorerAgent().run(
            "## CV Text\nAcme Engineer. Built ML pipeline with Python.", "jd " * 15, PRIOR
        )

    assert mock.await_count == 2  # one self-correction
    correction_system = mock.await_args_list[1].args[0]
    assert "## CORRECTION" in correction_system
    assert result.omitted_items[0].field == "skills"
