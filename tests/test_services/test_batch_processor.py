from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_discovery_batch_model_importable():
    from backend.models import DiscoveryBatch

    assert hasattr(DiscoveryBatch, "anthropic_batch_id")
    assert hasattr(DiscoveryBatch, "run_id")
    assert hasattr(DiscoveryBatch, "status")
    assert hasattr(DiscoveryBatch, "request_count")
    assert hasattr(DiscoveryBatch, "submitted_at")
    assert hasattr(DiscoveryBatch, "completed_at")


async def test_submit_stage2_batch_builds_correct_request_list():
    """submit_stage2_batch calls batches.create with one request dict per job."""
    from backend.services.batch_processor import submit_stage2_batch

    mock_batch = MagicMock()
    mock_batch.id = "msgbatch_test001"

    mock_client = MagicMock()
    mock_client.beta.messages.batches.create = AsyncMock(return_value=mock_batch)

    batch_id = await submit_stage2_batch(
        client=mock_client,
        jobs=[("job_aaa", "Python engineer wanted"), ("job_bbb", "Sales director role")],
        compact_profile="Alice is a backend engineer with Python and FastAPI.",
    )

    assert batch_id == "msgbatch_test001"
    call_kwargs = mock_client.beta.messages.batches.create.call_args.kwargs
    reqs = call_kwargs["requests"]
    assert len(reqs) == 2
    assert reqs[0]["custom_id"] == "job_aaa"
    assert reqs[1]["custom_id"] == "job_bbb"
    # system is a plain string (no cache_control — not supported by Batch API)
    assert isinstance(reqs[0]["params"]["system"], str)
    assert "Alice" in reqs[0]["params"]["system"]


async def test_poll_returns_immediately_when_ended():
    """poll_batch_until_done exits on the first call if status is already ended."""
    from backend.services.batch_processor import poll_batch_until_done

    ended = MagicMock()
    ended.processing_status = "ended"
    mock_client = MagicMock()
    mock_client.beta.messages.batches.retrieve = AsyncMock(return_value=ended)

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)

    import unittest.mock as _m

    with _m.patch("backend.services.batch_processor.asyncio.sleep", fake_sleep):
        await poll_batch_until_done(mock_client, "msgbatch_test001")

    assert sleep_calls == [], "Should not sleep when batch is already ended"
    mock_client.beta.messages.batches.retrieve.assert_called_once_with("msgbatch_test001")


async def test_poll_retries_while_in_progress():
    """poll_batch_until_done polls again after sleeping when status is in_progress."""
    from backend.services.batch_processor import poll_batch_until_done

    in_progress = MagicMock(processing_status="in_progress")
    ended = MagicMock(processing_status="ended")
    mock_client = MagicMock()
    mock_client.beta.messages.batches.retrieve = AsyncMock(side_effect=[in_progress, ended])

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)

    import unittest.mock as _m

    with _m.patch("backend.services.batch_processor.asyncio.sleep", fake_sleep):
        await poll_batch_until_done(mock_client, "msgbatch_test001")

    assert mock_client.beta.messages.batches.retrieve.call_count == 2
    assert len(sleep_calls) == 1


async def test_poll_raises_timeout_after_max_polls():
    """poll_batch_until_done raises TimeoutError after max_polls exceeded."""
    from backend.services.batch_processor import poll_batch_until_done

    in_progress = MagicMock(processing_status="in_progress")
    mock_client = MagicMock()
    mock_client.beta.messages.batches.retrieve = AsyncMock(return_value=in_progress)

    async def fake_sleep(_):
        pass

    import unittest.mock as _m

    with _m.patch("backend.services.batch_processor.asyncio.sleep", fake_sleep):
        with pytest.raises(TimeoutError, match="msgbatch_test001"):
            await poll_batch_until_done(mock_client, "msgbatch_test001", max_polls=3)


async def test_poll_continues_through_canceling():
    """poll_batch_until_done keeps polling when status is 'canceling' (transient, not terminal)."""
    from backend.services.batch_processor import poll_batch_until_done

    canceling = MagicMock(processing_status="canceling")
    ended = MagicMock(processing_status="ended")
    mock_client = MagicMock()
    mock_client.beta.messages.batches.retrieve = AsyncMock(side_effect=[canceling, ended])

    sleep_calls = []

    async def fake_sleep(n):
        sleep_calls.append(n)

    import unittest.mock as _m

    with _m.patch("backend.services.batch_processor.asyncio.sleep", fake_sleep):
        await poll_batch_until_done(mock_client, "msgbatch_test001")

    assert mock_client.beta.messages.batches.retrieve.call_count == 2
    assert len(sleep_calls) == 1  # slept once between the two polls


async def test_iter_batch_results_yields_stage2result_on_success():
    """iter_batch_results yields (job_id, Stage2Result, input_tokens, output_tokens) on success."""
    from anthropic.types.beta import BetaTextBlock

    from backend.services.batch_processor import iter_batch_results
    from backend.services.discovery import Stage2Result

    succeeded = MagicMock()
    succeeded.custom_id = "job_xyz"
    succeeded.result.type = "succeeded"
    succeeded.result.message.content = [
        BetaTextBlock(
            type="text",
            text='{"relevant": true, "reason": "good fit", "title": "Python Engineer", '
            '"company": "Acme", "location": "London"}',
        )
    ]
    succeeded.result.message.usage.input_tokens = 120
    succeeded.result.message.usage.output_tokens = 45

    async def mock_results(batch_id):
        async def _gen():
            yield succeeded

        return _gen()

    mock_client = MagicMock()
    mock_client.beta.messages.batches.results = mock_results

    collected = []
    async for item in iter_batch_results(mock_client, "msgbatch_test001"):
        collected.append(item)

    assert len(collected) == 1
    job_id, s2, in_toks, out_toks = collected[0]
    assert job_id == "job_xyz"
    assert isinstance(s2, Stage2Result)
    assert s2.relevant is True
    assert s2.title == "Python Engineer"
    assert s2.company == "Acme"
    assert s2.location == "London"
    assert in_toks == 120
    assert out_toks == 45


async def test_iter_batch_results_yields_none_on_errored():
    """iter_batch_results yields (job_id, None, 0, 0) for errored results."""
    from backend.services.batch_processor import iter_batch_results

    errored = MagicMock()
    errored.custom_id = "job_fail"
    errored.result.type = "errored"

    async def mock_results(batch_id):
        async def _gen():
            yield errored

        return _gen()

    mock_client = MagicMock()
    mock_client.beta.messages.batches.results = mock_results

    collected = []
    async for item in iter_batch_results(mock_client, "msgbatch_test001"):
        collected.append(item)

    job_id, s2, in_toks, out_toks = collected[0]
    assert job_id == "job_fail"
    assert s2 is None
    assert in_toks == 0
    assert out_toks == 0


async def test_iter_batch_results_yields_none_on_malformed_stage2_json():
    from anthropic.types.beta import BetaTextBlock

    from backend.services.batch_processor import iter_batch_results

    succeeded = MagicMock()
    succeeded.custom_id = "job_bad_json"
    succeeded.result.type = "succeeded"
    succeeded.result.message.content = [
        BetaTextBlock(type="text", text='{"reason": "missing required relevant"}')
    ]
    succeeded.result.message.usage.input_tokens = 10
    succeeded.result.message.usage.output_tokens = 5

    async def mock_results(batch_id):
        async def _gen():
            yield succeeded

        return _gen()

    mock_client = MagicMock()
    mock_client.beta.messages.batches.results = mock_results

    collected = []
    async for item in iter_batch_results(mock_client, "msgbatch_test001"):
        collected.append(item)

    job_id, s2, in_toks, out_toks = collected[0]
    assert job_id == "job_bad_json"
    assert s2 is None
    assert in_toks == 0
    assert out_toks == 0


async def test_log_batch_llm_call_writes_at_batch_rates(Session):
    """log_batch_llm_call writes LLMCall with 50% cost and latency_ms=0."""
    from sqlalchemy import select

    from backend.models import LLMCall
    from backend.services.instrumentation import log_batch_llm_call

    async with Session() as db:
        await log_batch_llm_call(
            db,
            agent_name="stage2_haiku_batch",
            model="claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=0,
        )

    async with Session() as db:
        call = (await db.execute(select(LLMCall))).scalar_one()

    assert call.agent_name == "stage2_haiku_batch"
    assert call.latency_ms == 0
    assert call.cache_hit is False
    # Batch rate: $0.40/M (50% of Haiku $0.80/M input)
    assert call.cost_usd == pytest.approx(0.40)
