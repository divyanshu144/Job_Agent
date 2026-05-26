# tests/test_services/test_instrumentation.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.instrumentation import tracked_call, log_cache_hit


@pytest.fixture
def mock_client():
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="response text")]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    client.messages.create = AsyncMock(return_value=msg)
    return client, msg


@pytest.mark.asyncio
async def test_tracked_call_returns_message(mock_client):
    client, msg = mock_client
    result = await tracked_call(client, "test_agent", "claude-sonnet-4-6", system="s", messages=[])
    assert result is msg


@pytest.mark.asyncio
async def test_tracked_call_without_db_does_not_raise(mock_client):
    client, _ = mock_client
    # db=None is the default — must not raise
    await tracked_call(client, "test_agent", "claude-sonnet-4-6", system="s", messages=[])


@pytest.mark.asyncio
async def test_tracked_call_db_failure_does_not_raise(mock_client):
    client, _ = mock_client
    bad_db = MagicMock()
    bad_db.add = MagicMock()
    bad_db.commit = AsyncMock(side_effect=Exception("DB is down"))
    # must return message even when DB write fails
    result = await tracked_call(
        client, "test_agent", "claude-sonnet-4-6", db=bad_db, system="s", messages=[]
    )
    assert result.content[0].text == "response text"


@pytest.mark.asyncio
async def test_log_cache_hit_db_failure_does_not_raise():
    bad_db = MagicMock()
    bad_db.add = MagicMock()
    bad_db.commit = AsyncMock(side_effect=Exception("DB is down"))
    # must not raise
    await log_cache_hit(bad_db, "match_scorer", "claude-sonnet-4-6")
