import json
from unittest.mock import patch

import pytest

from backend.schemas import GapAnalystOutput, GapItem, PriorOutputs, ResourcePlannerOutput

PRIOR = PriorOutputs(
    gap_analyst=GapAnalystOutput(
        critical_gaps=[GapItem(skill="Kubernetes", impact="required", rationale="core")],
        nice_to_have_gaps=[],
    )
)
HAPPY = json.dumps(
    {
        "gaps": [
            {
                "skill": "Kubernetes",
                "courses": ["K8s Basics (CNCF)"],
                "books": [],
                "projects": ["Deploy a FastAPI app to a local k3s cluster"],
                "estimated_hours": 20,
            }
        ]
    }
)
MALFORMED = [HAPPY[:10], json.dumps({"gaps": "not-a-list"})]


async def test_resource_planner_happy():
    from backend.agents.resource_planner import ResourcePlannerAgent

    async def _call(self, s, u):
        return HAPPY

    with patch.object(ResourcePlannerAgent, "_call", new=_call):
        result = await ResourcePlannerAgent().run("profile", "jd " * 15, PRIOR)
    assert isinstance(result, ResourcePlannerOutput)
    assert result.gaps[0].skill == "Kubernetes"
    assert result.gaps[0].estimated_hours == 20


@pytest.mark.parametrize("bad", MALFORMED)
async def test_resource_planner_malformed(bad):
    from backend.agents.job_parser import AgentError
    from backend.agents.resource_planner import ResourcePlannerAgent

    async def _call(self, s, u):
        return bad

    with patch.object(ResourcePlannerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ResourcePlannerAgent().run("profile", "jd " * 15, PRIOR)
