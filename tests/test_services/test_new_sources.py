# tests/test_services/test_new_sources.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx


def _mock_client(responses: list[object] | object) -> AsyncMock:
    """Build a mock httpx.AsyncClient. `responses` is one response or a list
    returned in order across successive .get() calls."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    if isinstance(responses, list):
        seq = iter(responses)

        async def fake_get(url: str, params: object = None) -> object:
            return next(seq)

        client.get = fake_get
    else:

        async def fake_get_single(url: str, params: object = None) -> object:
            return responses

        client.get = fake_get_single
    return client


def _resp(payload: object) -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload)
    return r


# ───────────────────────────── Remotive ──────────────────────────────


async def test_fetch_remotive_jobs_happy_path():
    from backend.services import remotive_client

    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Senior Backend Engineer",
                "company_name": "Remotive Co",
                "candidate_required_location": "Worldwide",
                "url": "https://remotive.com/jobs/123",
                "description": (
                    "<p>We need a Python engineer with FastAPI and PostgreSQL "
                    "experience. 5+ years required. Fully remote role.</p>"
                ),
            }
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_resp(payload))):
        jobs = await remotive_client.fetch_remotive_jobs()

    assert len(jobs) == 1
    assert jobs[0].source_id == "remotive_123"
    assert jobs[0].source_url == "https://remotive.com/jobs/123"
    assert "Senior Backend Engineer" in jobs[0].raw_text
    assert "Remotive Co" in jobs[0].raw_text
    assert "<p>" not in jobs[0].raw_text  # HTML stripped
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_remotive_jobs_http_error_returns_empty():
    from backend.services import remotive_client

    client = _mock_client(_resp({}))
    client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    with patch("httpx.AsyncClient", return_value=client):
        jobs = await remotive_client.fetch_remotive_jobs()
    assert jobs == []


async def test_fetch_remotive_jobs_drops_short_text():
    from backend.services import remotive_client

    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Dev",
                "company_name": "Co",
                "candidate_required_location": "Remote",
                "url": "https://remotive.com/jobs/1",
                "description": "Short.",
            }
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_resp(payload))):
        jobs = await remotive_client.fetch_remotive_jobs()
    assert jobs == []


# ──────────────────────────── ATS detect ─────────────────────────────


def test_detect_ats_recognises_each_provider():
    from backend.services.ats_client import detect_ats

    assert detect_ats("https://boards.greenhouse.io/stripe") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/netlify") == "lever"
    assert detect_ats("https://jobs.ashbyhq.com/ramp") == "ashby"


def test_detect_ats_unknown_returns_none():
    from backend.services.ats_client import detect_ats

    assert detect_ats("https://careers.example.com/jobs") is None
    assert detect_ats("") is None


# ──────────────────────────── ATS fetch ──────────────────────────────


async def test_fetch_ats_jobs_greenhouse():
    from backend.services import ats_client

    # content arrives HTML-escaped from the real Greenhouse API (&lt;p&gt; …)
    payload = {
        "jobs": [
            {
                "id": 4567,
                "title": "Staff Software Engineer",
                "location": {"name": "Remote - US"},
                "absolute_url": "https://stripe.com/jobs/search?gh_jid=4567",
                "content": (
                    "&lt;h2&gt;About the role&lt;/h2&gt;&lt;p&gt;Build payments "
                    "infrastructure at scale with Go and Ruby. We value strong "
                    "distributed-systems fundamentals here.&lt;/p&gt;"
                ),
            }
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_resp(payload))):
        jobs = await ats_client.fetch_ats_jobs("greenhouse", "stripe")

    assert len(jobs) == 1
    assert jobs[0].source_id == "greenhouse_stripe_4567"
    assert jobs[0].source_url == "https://stripe.com/jobs/search?gh_jid=4567"
    assert "Staff Software Engineer" in jobs[0].raw_text
    assert "Build payments infrastructure" in jobs[0].raw_text
    # escaped HTML must be unescaped AND stripped — no tags, no entities left
    assert "<" not in jobs[0].raw_text and "&lt;" not in jobs[0].raw_text
    assert len(jobs[0].dedup_hash) == 64


async def test_fetch_ats_jobs_lever():
    from backend.services import ats_client

    payload = [
        {
            "id": "abc-123",
            "text": "Senior Frontend Engineer",
            "categories": {"location": "Remote", "team": "Web"},
            "hostedUrl": "https://jobs.lever.co/netlify/abc-123",
            "descriptionPlain": (
                "Own the component library and build delightful UIs with React "
                "and TypeScript. Collaborate closely with design."
            ),
        }
    ]
    with patch("httpx.AsyncClient", return_value=_mock_client(_resp(payload))):
        jobs = await ats_client.fetch_ats_jobs("lever", "netlify")

    assert len(jobs) == 1
    assert jobs[0].source_id == "lever_netlify_abc-123"
    assert jobs[0].source_url == "https://jobs.lever.co/netlify/abc-123"
    assert "Senior Frontend Engineer" in jobs[0].raw_text


async def test_fetch_ats_jobs_ashby():
    from backend.services import ats_client

    payload = {
        "jobs": [
            {
                "id": "xyz-9",
                "title": "Backend Engineer",
                "location": "New York",
                "jobUrl": "https://jobs.ashbyhq.com/ramp/xyz-9",
                "descriptionPlain": (
                    "Design and ship financial APIs in Python. Care about "
                    "correctness, latency, and clean abstractions."
                ),
            }
        ]
    }
    with patch("httpx.AsyncClient", return_value=_mock_client(_resp(payload))):
        jobs = await ats_client.fetch_ats_jobs("ashby", "ramp")

    assert len(jobs) == 1
    assert jobs[0].source_id == "ashby_ramp_xyz-9"
    assert jobs[0].source_url == "https://jobs.ashbyhq.com/ramp/xyz-9"
    assert "Backend Engineer" in jobs[0].raw_text


async def test_fetch_ats_jobs_http_error_returns_empty():
    from backend.services import ats_client

    client = _mock_client(_resp({}))
    client.get = AsyncMock(side_effect=httpx.HTTPError("502"))
    with patch("httpx.AsyncClient", return_value=client):
        jobs = await ats_client.fetch_ats_jobs("greenhouse", "stripe")
    assert jobs == []


# ───────────────────────────── Targets ───────────────────────────────


async def test_fetch_target_jobs_queries_each_entry(tmp_path):
    import json

    from backend.services import targets_client
    from backend.services.hn_client import RawJob

    target_file = tmp_path / "target_companies.json"
    target_file.write_text(
        json.dumps(
            [
                {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"},
                {"name": "Netlify", "ats": "lever", "slug": "netlify"},
            ]
        )
    )

    async def fake_fetch_ats(ats: str, slug: str) -> list[RawJob]:
        return [
            RawJob(
                source_id=f"{ats}_{slug}_1",
                source_url=f"https://x/{slug}/1",
                raw_text="role " * 30,
                dedup_hash=f"hash-{slug}",
            )
        ]

    with (
        patch.object(targets_client, "_TARGET_FILE", target_file),
        patch.object(targets_client, "fetch_ats_jobs", side_effect=fake_fetch_ats),
    ):
        jobs = await targets_client.fetch_target_jobs()

    assert {j.source_id for j in jobs} == {"greenhouse_stripe_1", "lever_netlify_1"}


async def test_fetch_target_jobs_missing_file_returns_empty(tmp_path):
    from backend.services import targets_client

    with patch.object(targets_client, "_TARGET_FILE", tmp_path / "nope.json"):
        jobs = await targets_client.fetch_target_jobs()
    assert jobs == []


async def test_fetch_target_jobs_skips_malformed_entry(tmp_path):
    import json

    from backend.services import targets_client
    from backend.services.hn_client import RawJob

    target_file = tmp_path / "target_companies.json"
    target_file.write_text(
        json.dumps(
            [
                {"name": "NoAts"},  # malformed: missing ats/slug
                {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"},
            ]
        )
    )

    async def fake_fetch_ats(ats: str, slug: str) -> list[RawJob]:
        return [
            RawJob(
                source_id=f"{ats}_{slug}_1",
                source_url="https://x/1",
                raw_text="role " * 30,
                dedup_hash="h",
            )
        ]

    with (
        patch.object(targets_client, "_TARGET_FILE", target_file),
        patch.object(targets_client, "fetch_ats_jobs", side_effect=fake_fetch_ats),
    ):
        jobs = await targets_client.fetch_target_jobs()

    assert len(jobs) == 1
    assert jobs[0].source_id == "greenhouse_stripe_1"


# ──────────────────────── configured sources ─────────────────────────


def test_get_configured_sources_includes_keyless_sources():
    from backend.services.discovery import _get_configured_sources

    sources = _get_configured_sources()
    assert "remotive" in sources
    assert "hn" in sources


def test_get_configured_sources_targets_gated_on_file():
    from backend.services import discovery

    with patch.object(discovery, "_target_list_present", return_value=True):
        assert "targets" in discovery._get_configured_sources()
    with patch.object(discovery, "_target_list_present", return_value=False):
        assert "targets" not in discovery._get_configured_sources()
