from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.agents.cold_email_agent import ColdEmailAgent
from backend.agents.job_parser import AgentError


@pytest.mark.asyncio
async def test_cold_email_agent_returns_output():
    agent = ColdEmailAgent()
    mock_response = '{"subject": "Excited about Stripe", "body": "Hi Alice,\\n\\nI loved..."}'

    with patch.object(agent, "_call", new=AsyncMock(return_value=mock_response)):
        result = await agent.run(
            profile="Software engineer with 5 years Python",
            jd="Stripe is hiring a backend engineer",
            contact_name="Alice Chen",
            contact_title="Engineering Manager",
        )

    assert result.subject == "Excited about Stripe"
    assert "Alice" in result.body


@pytest.mark.asyncio
async def test_cold_email_agent_handles_null_name_and_title():
    agent = ColdEmailAgent()
    mock_response = '{"subject": "Hello", "body": "Hi team, I noticed..."}'

    with patch.object(agent, "_call", new=AsyncMock(return_value=mock_response)):
        result = await agent.run(
            profile="Software engineer",
            jd="Company is hiring",
            contact_name=None,
            contact_title=None,
        )

    assert result.subject == "Hello"


@pytest.mark.asyncio
async def test_cold_email_agent_raises_on_bad_json():
    agent = ColdEmailAgent()

    with patch.object(agent, "_call", new=AsyncMock(return_value="not json at all")):
        with pytest.raises(AgentError):
            await agent.run("profile", "jd", "Name", "Title")
