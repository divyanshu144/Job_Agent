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


_TWO_GAP_PRIOR = PriorOutputs(
    gap_analyst=GapAnalystOutput(
        critical_gaps=[
            GapItem(skill="Kubernetes", impact="required", rationale="core"),
            GapItem(skill="Terraform", impact="required", rationale="core"),
        ],
        nice_to_have_gaps=[],
    )
)
_PASS1_TWO = json.dumps(
    {
        "gaps": [
            {
                "skill": "Kubernetes",
                "courses": ["K8s (CNCF)"],
                "books": [],
                "projects": ["k3s app"],
                "estimated_hours": 20,
            },
            {
                "skill": "Terraform",
                "courses": ["generic course"],
                "books": [],
                "projects": ["vague"],
                "estimated_hours": 10,
            },
        ]
    }
)


async def test_resource_planner_selfcheck_regenerates_low_confidence():
    from unittest.mock import AsyncMock

    from backend.agents.resource_planner import ResourcePlannerAgent

    selfcheck = json.dumps(
        {
            "scores": [
                {"skill": "Kubernetes", "confidence": 0.9},
                {"skill": "Terraform", "confidence": 0.4},
            ]
        }
    )
    pass2 = json.dumps(
        {
            "gaps": [
                {
                    "skill": "Terraform",
                    "courses": ["HashiCorp Learn: Terraform Associate"],
                    "books": [],
                    "projects": ["Provision a VPC with TF modules"],
                    "estimated_hours": 15,
                }
            ]
        }
    )
    mock = AsyncMock(side_effect=[_PASS1_TWO, selfcheck, pass2])
    with patch.object(ResourcePlannerAgent, "_call", new=mock):
        result = await ResourcePlannerAgent().run("profile", "jd " * 15, _TWO_GAP_PRIOR)

    assert {g.skill for g in result.gaps} == {"Kubernetes", "Terraform"}
    tf = next(g for g in result.gaps if g.skill == "Terraform")
    assert "HashiCorp" in tf.courses[0]  # regenerated in pass 2
    k8s = next(g for g in result.gaps if g.skill == "Kubernetes")
    assert k8s.courses == ["K8s (CNCF)"]  # kept from pass 1
    assert result.planner_meta is not None
    assert result.planner_meta.total_llm_calls == 3
    assert result.planner_meta.retried_gaps == ["Terraform"]
    assert result.planner_meta.low_confidence_gaps == ["Terraform"]
    assert mock.await_count == 3


async def test_resource_planner_selfcheck_skips_when_confident():
    from unittest.mock import AsyncMock

    from backend.agents.resource_planner import ResourcePlannerAgent

    selfcheck = json.dumps(
        {
            "scores": [
                {"skill": "Kubernetes", "confidence": 0.9},
                {"skill": "Terraform", "confidence": 0.8},
            ]
        }
    )
    mock = AsyncMock(side_effect=[_PASS1_TWO, selfcheck])
    with patch.object(ResourcePlannerAgent, "_call", new=mock):
        result = await ResourcePlannerAgent().run("profile", "jd " * 15, _TWO_GAP_PRIOR)

    assert result.planner_meta.total_llm_calls == 2
    assert result.planner_meta.retried_gaps == []
    assert result.planner_meta.low_confidence_gaps == []
    assert mock.await_count == 2  # no pass 2


@pytest.mark.parametrize("bad", MALFORMED)
async def test_resource_planner_malformed(bad):
    from backend.agents.job_parser import AgentError
    from backend.agents.resource_planner import ResourcePlannerAgent

    async def _call(self, s, u):
        return bad

    with patch.object(ResourcePlannerAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ResourcePlannerAgent().run("profile", "jd " * 15, PRIOR)
