from backend.agents.base import HAIKU, SONNET, BaseAgent
from backend.agents.cover_letter import CoverLetterAgent
from backend.agents.gap_analyst import GapAnalystAgent
from backend.agents.job_parser import JobParserAgent
from backend.agents.match_scorer import MatchScorerAgent
from backend.agents.resource_planner import ResourcePlannerAgent
from backend.agents.resume_tailorer import ResumeTailorerAgent


def test_haiku_agents():
    assert JobParserAgent.model == HAIKU
    assert MatchScorerAgent.model == HAIKU


def test_sonnet_agents():
    assert GapAnalystAgent.model == SONNET
    assert ResourcePlannerAgent.model == SONNET
    assert CoverLetterAgent.model == SONNET
    assert ResumeTailorerAgent.model == SONNET


def test_base_agent_defaults_to_sonnet():
    assert BaseAgent.model == SONNET
