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

    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call

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
    assert row.cost_usd == pytest.approx((100 * 0.80 + 20 * 4.00 + 800 * 1.00) / 1_000_000)


@pytest.mark.asyncio
async def test_tracked_call_records_cache_read_tokens(db_session):
    """cache_read_input_tokens from response are stored and discounted in cost."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call

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
    assert row.cost_usd == pytest.approx((50 * 0.80 + 10 * 4.00 + 600 * 0.08) / 1_000_000)


@pytest.mark.asyncio
async def test_tracked_call_handles_none_cache_usage(db_session):
    """If cache token fields are None (caching not used), store 0 without error."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call

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


@pytest.mark.asyncio
async def test_tracked_call_records_prompt_version_metadata(db_session):
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call

    mock_usage = MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 10
    mock_usage.cache_creation_input_tokens = 0
    mock_usage.cache_read_input_tokens = 0

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "job_parser",
        "claude-haiku-4-5-20251001",
        db=db_session,
        prompt_name="job_parser",
        prompt_hash="b" * 64,
        prompt_version="sha256:" + "b" * 12,
        max_tokens=256,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.prompt_name == "job_parser"
    assert row.prompt_hash == "b" * 64
    assert row.prompt_version == "sha256:" + "b" * 12


@pytest.mark.asyncio
async def test_log_batch_llm_call_records_prompt_version_metadata(db_session):
    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import log_batch_llm_call

    await log_batch_llm_call(
        db_session,
        "stage2_haiku_batch",
        "claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=20,
        prompt_name="discovery_stage2",
        prompt_hash="c" * 64,
        prompt_version="sha256:" + "c" * 12,
    )

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.prompt_name == "discovery_stage2"
    assert row.prompt_hash == "c" * 64
    assert row.prompt_version == "sha256:" + "c" * 12


@pytest.mark.asyncio
async def test_tracked_call_increments_llm_calls_counter(mock_client):
    from prometheus_client import REGISTRY

    labels = {"agent": "counter_agent", "model": "counter-model"}
    before = REGISTRY.get_sample_value("llm_calls_total", labels) or 0.0
    client, _ = mock_client
    await tracked_call(client, "counter_agent", "counter-model", system="s", messages=[])
    assert REGISTRY.get_sample_value("llm_calls_total", labels) == before + 1


@pytest.mark.asyncio
async def test_cache_hit_does_not_increment_llm_calls_counter(db_session):
    from prometheus_client import REGISTRY

    labels = {"agent": "cache_agent", "model": "cache-model"}
    before = REGISTRY.get_sample_value("llm_calls_total", labels) or 0.0
    await log_cache_hit(db_session, "cache_agent", "cache-model")
    assert (REGISTRY.get_sample_value("llm_calls_total", labels) or 0.0) == before
