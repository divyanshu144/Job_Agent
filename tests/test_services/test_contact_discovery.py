from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.models  # noqa: F401
from backend.models import Analysis, JobResult, Profile
from backend.services.contact_discovery import (
    ContactDiscoveryUnavailable,
    _title_rank,
    discover_contacts,
)


@pytest.fixture
async def analysis_with_jp(session):
    """Insert a Profile, Analysis, and job_parser JobResult with company='Stripe'."""
    profile = Profile(
        id="prof-1",
        yaml_data="",
        cv_text="",
        merged_profile="test profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()  # PG enforces FKs; insert parent before children
    analysis = Analysis(
        id="anal-1",
        jd_text="test jd",
        profile_id="prof-1",
        created_at=datetime.now(timezone.utc),
        partial=False,
    )
    session.add(analysis)
    await session.flush()
    jp = JobResult(
        id="jr-1",
        analysis_id="anal-1",
        agent_name="job_parser",
        output_json=json.dumps(
            {
                "company": "Stripe",
                "required_skills": [],
                "nice_to_have": [],
                "role_type": "Engineering",
                "seniority": "Senior",
            }
        ),
    )
    session.add(jp)
    await session.commit()
    return analysis


def test_title_rank_hiring_manager():
    assert _title_rank("Senior Hiring Manager") == 0


def test_title_rank_unknown():
    assert _title_rank("Data Analyst") == 4  # len(TITLE_PRIORITY)


def test_title_rank_none():
    assert _title_rank(None) == 4


@pytest.mark.asyncio
async def test_discover_contacts_happy_path(analysis_with_jp, session):
    hunter_response = {
        "data": {
            "emails": [
                {
                    "value": "alice@stripe.com",
                    "first_name": "Alice",
                    "last_name": "Chen",
                    "position": "Engineering Manager",
                    "confidence": 94,
                },
                {
                    "value": "bob@stripe.com",
                    "first_name": "Bob",
                    "last_name": "Smith",
                    "position": "Recruiter",
                    "confidence": 72,
                },
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", session)

    assert len(contacts) == 2
    assert contacts[0].email == "alice@stripe.com"  # Engineering Manager ranked higher
    assert contacts[0].confidence == pytest.approx(0.94)
    assert contacts[0].status == "discovered"
    assert contacts[0].source == "hunter"


@pytest.mark.asyncio
async def test_discover_contacts_filters_no_email(analysis_with_jp, session):
    hunter_response = {
        "data": {
            "emails": [
                {"value": "alice@stripe.com", "confidence": 90, "position": "Recruiter"},
                {"value": "", "confidence": 80, "position": "Engineer"},  # no email — filtered
                {"confidence": 70, "position": "Manager"},  # missing value key — filtered
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", session)

    assert len(contacts) == 1
    assert contacts[0].email == "alice@stripe.com"


@pytest.mark.asyncio
async def test_discover_contacts_raises_on_http_error(analysis_with_jp, session):
    import httpx

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(ContactDiscoveryUnavailable):
            await discover_contacts("anal-1", session)


@pytest.mark.asyncio
async def test_discover_contacts_raises_domain_required_when_no_company(session):
    profile = Profile(
        id="prof-2",
        yaml_data="",
        cv_text="",
        merged_profile="",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.flush()  # PG enforces FKs; insert parent before children
    analysis = Analysis(
        id="anal-2",
        jd_text="test jd",
        profile_id="prof-2",
        created_at=datetime.now(timezone.utc),
        partial=False,
    )
    session.add(analysis)
    await session.flush()
    jp = JobResult(
        id="jr-2",
        analysis_id="anal-2",
        agent_name="job_parser",
        output_json=json.dumps(
            {
                "company": None,
                "required_skills": [],
                "nice_to_have": [],
                "role_type": "Engineering",
                "seniority": "Senior",
            }
        ),
    )
    session.add(jp)
    await session.commit()

    with pytest.raises(ValueError, match="domain_required"):
        await discover_contacts("anal-2", session, domain=None)


@pytest.mark.asyncio
async def test_discover_contacts_uses_supplied_domain(analysis_with_jp, session):
    hunter_response = {
        "data": {
            "emails": [
                {"value": "carol@customdomain.io", "confidence": 85, "position": "Founder"},
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = hunter_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        contacts = await discover_contacts("anal-1", session, domain="customdomain.io")

    # Verify Hunter.io was called with the supplied domain
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["domain"] == "customdomain.io"
    assert len(contacts) == 1


@pytest.mark.asyncio
async def test_discover_contacts_raises_on_request_error(analysis_with_jp, session):
    import httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection timeout"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(ContactDiscoveryUnavailable):
            await discover_contacts("anal-1", session)
