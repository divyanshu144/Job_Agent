# tests/test_services/test_reed_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


async def test_fetch_reed_jobs_returns_empty_when_key_missing():
    """Returns [] immediately if reed_api_key is empty — no HTTP call made."""
    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = ""
        from backend.services.reed_client import fetch_reed_jobs
        jobs = await fetch_reed_jobs("python engineer", "london")
    assert jobs == []


async def test_fetch_reed_jobs_happy_path():
    """One result in first page, empty second page → one RawJob returned."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "jobId": 42,
            "jobTitle": "Senior Python Engineer",
            "employerName": "Acme Corp",
            "locationName": "London",
            "jobDescription": (
                "We need a Python engineer with FastAPI and PostgreSQL experience "
                "for our platform team. 5+ years required. Remote friendly."
            ),
            "jobUrl": "https://www.reed.co.uk/jobs/senior-python-engineer/42",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python engineer", "london")

    assert len(jobs) == 1
    assert jobs[0].source_id == "reed_42"
    assert "Senior Python Engineer" in jobs[0].raw_text
    assert "Acme Corp" in jobs[0].raw_text
    assert jobs[0].source_url == "https://www.reed.co.uk/jobs/senior-python-engineer/42"
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_reed_jobs_http_error_returns_empty():
    """HTTP error on first page → returns [] gracefully."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python", "")

    assert jobs == []


async def test_fetch_reed_jobs_skips_short_descriptions():
    """Jobs whose combined text is < 100 chars are dropped."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "jobId": 99,
            "jobTitle": "Dev",
            "employerName": "Co",
            "locationName": "London",
            "jobDescription": "Short.",
            "jobUrl": "https://www.reed.co.uk/jobs/dev/99",
        }],
    })
    page2 = MagicMock()
    page2.raise_for_status = MagicMock()
    page2.json = MagicMock(return_value={"results": []})

    call_count = 0
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async def fake_get(url: str, params: object = None) -> object:
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    mock_client.get = fake_get

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.reed_api_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import reed_client
            importlib.reload(reed_client)
            jobs = await reed_client.fetch_reed_jobs("python", "london")

    assert jobs == []
