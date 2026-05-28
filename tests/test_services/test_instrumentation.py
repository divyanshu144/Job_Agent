# tests/test_services/test_instrumentation.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.instrumentation import log_cache_hit, tracked_call


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


@pytest.mark.asyncio
async def test_tracked_call_records_cache_creation_tokens(db_session):
    """cache_creation_input_tokens from response are stored in LLMCall row."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 20
    mock_usage.cache_creation_input_tokens = 800
    mock_usage.cache_read_input_tokens = 0

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system=[{"type": "text", "text": "sys"}],
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_creation_tokens == 800
    assert row.cache_read_tokens == 0
    # Cost: 100 input ($0.80/M) + 20 output ($4.00/M) + 800 cache_write ($1.00/M)
    assert row.cost_usd == pytest.approx(
        (100 * 0.80 + 20 * 4.00 + 800 * 1.00) / 1_000_000
    )


@pytest.mark.asyncio
async def test_tracked_call_records_cache_read_tokens(db_session):
    """cache_read_input_tokens from response are stored and discounted in cost."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 10
    mock_usage.cache_creation_input_tokens = 0
    mock_usage.cache_read_input_tokens = 600

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system=[{"type": "text", "text": "sys"}],
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_read_tokens == 600
    # Cost: 50 input + 10 output + 600 cache_read ($0.08/M)
    assert row.cost_usd == pytest.approx(
        (50 * 0.80 + 10 * 4.00 + 600 * 0.08) / 1_000_000
    )


@pytest.mark.asyncio
async def test_tracked_call_handles_none_cache_usage(db_session):
    """If cache token fields are None (caching not used), store 0 without error."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 30
    mock_usage.cache_creation_input_tokens = None
    mock_usage.cache_read_input_tokens = None

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_creation_tokens == 0
    assert row.cache_read_tokens == 0
