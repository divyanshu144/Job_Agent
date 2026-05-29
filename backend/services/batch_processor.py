from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from backend.agents.base import HAIKU
from backend.services.discovery import Stage2Result

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

_STAGE2_SYSTEM_TEMPLATE = (
    "You are evaluating job postings for a candidate.\n\n"
    "Candidate summary:\n{compact_profile}\n\n"
    "Evaluate if the job posting is relevant to this candidate. "
    'Respond with ONLY valid JSON: {{"relevant": true/false, "reason": "one sentence", '
    '"title": "job title or empty string", "company": "company name or empty string", '
    '"location": "city/remote or null"}}'
)

_POLL_INTERVAL_SECONDS = 60


async def submit_stage2_batch(
    client: anthropic.AsyncAnthropic,
    jobs: list[tuple[str, str]],  # [(job_id, raw_text), ...]
    compact_profile: str,
) -> str:
    """Submit all Stage 2 relevance checks as one Anthropic Batch API request.

    Returns the Anthropic batch id (e.g. "msgbatch_01...").
    cache_control is intentionally omitted — Batch API does not support prompt caching.
    """
    system = _STAGE2_SYSTEM_TEMPLATE.format(compact_profile=compact_profile[:1000])
    requests = [
        {
            "custom_id": job_id,
            "params": {
                "model": HAIKU,
                "max_tokens": 200,
                "system": system,
                "messages": [{"role": "user", "content": f"Job posting:\n{raw_text[:3000]}"}],
            },
        }
        for job_id, raw_text in jobs
    ]
    batch = await client.beta.messages.batches.create(requests=requests)
    logger.info("Submitted Batch API request: %d jobs → %s", len(jobs), batch.id)
    return batch.id


async def poll_batch_until_done(
    client: anthropic.AsyncAnthropic,
    batch_id: str,
    *,
    max_polls: int = 720,  # 12 hours at 60-second intervals
) -> None:
    """Poll Anthropic until processing_status == 'ended'.

    Raises TimeoutError after max_polls attempts.
    Raises RuntimeError if the batch enters a terminal error state (canceling/expired).
    """
    for attempt in range(max_polls):
        batch = await client.beta.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            logger.info("Batch %s completed (poll %d)", batch_id, attempt + 1)
            return
        if batch.processing_status in ("canceling", "expired"):
            raise RuntimeError(
                f"Batch {batch_id} entered terminal state: {batch.processing_status}"
            )
        logger.debug(
            "Batch %s: %s (poll %d/%d)", batch_id, batch.processing_status, attempt + 1, max_polls
        )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise TimeoutError(
        f"Batch {batch_id} did not complete within {max_polls} polls "
        f"({max_polls * _POLL_INTERVAL_SECONDS}s)"
    )


async def iter_batch_results(
    client: anthropic.AsyncAnthropic,
    batch_id: str,
) -> AsyncGenerator[tuple[str, Stage2Result | None, int, int], None]:
    """Stream batch results.

    Yields (job_id, Stage2Result, input_tokens, output_tokens) on success.
    Yields (job_id, None, 0, 0) on errored/canceled/expired results or JSON parse failure.
    """
    decoder = await client.beta.messages.batches.results(batch_id)
    async for item in decoder:
        job_id = item.custom_id
        if item.result.type != "succeeded":
            logger.warning("Batch result for job %s: type=%s", job_id, item.result.type)
            yield job_id, None, 0, 0
            continue
        try:
            raw = item.result.message.content[0].text.strip()
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError(f"No JSON object in response: {raw!r}")
            data = json.loads(raw[start:end])
            s2 = Stage2Result(
                relevant=bool(data.get("relevant", False)),
                reason=data.get("reason", ""),
                title=data.get("title", ""),
                company=data.get("company", ""),
                location=data.get("location"),
            )
            usage = item.result.message.usage
            yield job_id, s2, usage.input_tokens, usage.output_tokens
        except Exception as exc:
            logger.warning("Failed to parse Stage2Result for job %s: %s", job_id, exc)
            yield job_id, None, 0, 0
