# tests/test_services/test_adzuna_client.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


async def test_fetch_adzuna_jobs_returns_empty_when_creds_missing():
    """Returns [] immediately if adzuna_app_id or adzuna_app_key is empty."""
    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = ""
        mock_cfg.adzuna_app_key = "key"
        from backend.services.adzuna_client import fetch_adzuna_jobs
        jobs = await fetch_adzuna_jobs("python", "london")
    assert jobs == []


async def test_fetch_adzuna_jobs_happy_path():
    """One result on page 1, empty page 2 → one RawJob."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "id": "adzuna-123",
            "title": "Backend Engineer",
            "company": {"display_name": "TechCo"},
            "location": {"display_name": "London"},
            "description": (
                "We are looking for a backend engineer with Python, FastAPI, "
                "PostgreSQL, and AWS experience to join our product team. "
                "5+ years required. Remote-friendly within EU."
            ),
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/adzuna-123",
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
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert len(jobs) == 1
    assert jobs[0].source_id == "adzuna_adzuna-123"
    assert "Backend Engineer" in jobs[0].raw_text
    assert "TechCo" in jobs[0].raw_text
    assert jobs[0].source_url == "https://www.adzuna.co.uk/jobs/details/adzuna-123"
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_adzuna_jobs_http_error_returns_empty():
    """HTTP error → returns [] gracefully."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))

    with patch("backend.config.settings") as mock_cfg:
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert jobs == []


async def test_fetch_adzuna_jobs_skips_short_descriptions():
    """Jobs with combined text < 100 chars are dropped."""
    page1 = MagicMock()
    page1.raise_for_status = MagicMock()
    page1.json = MagicMock(return_value={
        "results": [{
            "id": "short-1",
            "title": "Dev",
            "company": {"display_name": "Co"},
            "location": {"display_name": "London"},
            "description": "Short.",
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/short-1",
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
        mock_cfg.adzuna_app_id = "test-id"
        mock_cfg.adzuna_app_key = "test-key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            import importlib

            from backend.services import adzuna_client
            importlib.reload(adzuna_client)
            jobs = await adzuna_client.fetch_adzuna_jobs("python", "london")

    assert jobs == []
