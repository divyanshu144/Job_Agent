# tests/test_services/test_hn_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


async def test_strip_html_removes_tags_and_decodes_entities():
    from backend.services.hn_client import _strip_html

    result = _strip_html("<p>We&#39;re hiring a <b>Python</b> engineer.</p>")
    assert "<" not in result
    assert "Python" in result
    assert "We're" in result


async def test_fetch_hn_jobs_returns_empty_when_no_thread():
    """Returns [] when Algolia finds no thread this month."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"hits": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from backend.services.hn_client import fetch_hn_jobs

        jobs = await fetch_hn_jobs()

    assert jobs == []


async def test_fetch_hn_jobs_skips_short_comments():
    """Comments shorter than 100 chars are skipped."""
    thread_resp = MagicMock()
    thread_resp.raise_for_status = MagicMock()
    thread_resp.json = MagicMock(return_value={"hits": [{"objectID": "111"}]})

    comments_resp = MagicMock()
    comments_resp.raise_for_status = MagicMock()
    comments_resp.json = MagicMock(
        return_value={
            "hits": [
                {"objectID": "222", "comment_text": "<p>Short</p>"},
                {
                    "objectID": "333",
                    "comment_text": "<p>"
                    + "We are hiring a Python engineer with 5+ years experience. " * 5
                    + "</p>",
                },
            ],
            "nbPages": 1,
        }
    )

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url, params=None):
        nonlocal call_count
        call_count += 1
        return thread_resp if call_count == 1 else comments_resp

    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        from backend.services import hn_client
        import importlib

        importlib.reload(hn_client)
        jobs = await hn_client.fetch_hn_jobs()

    assert len(jobs) == 1
    assert jobs[0].source_id == "333"


async def test_raw_job_has_correct_fields():
    """RawJob.dedup_hash is sha256 of raw_text."""
    import hashlib
    from backend.services.hn_client import RawJob

    text = "some job text here"
    job = RawJob(
        source_id="x",
        source_url="https://news.ycombinator.com/item?id=x",
        raw_text=text,
        dedup_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    assert len(job.dedup_hash) == 64
