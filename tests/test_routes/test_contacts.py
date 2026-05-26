from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from backend.models import Analysis, Contact, JobResult, Profile, User
from backend.services.auth_service import get_current_user


@pytest.fixture
def fake_user():
    return User(
        id="user-1",
        email="test@test.com",
        hashed_password="x",
        is_active=True,
        is_admin=False,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def authed_client(app_client, fake_user):
    from backend.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def seeded_analysis(db_session):
    """Insert Profile, Analysis, JobResult(job_parser) with company='Stripe'."""
    profile = Profile(
        id="prof-1",
        yaml_data="",
        cv_text="",
        github_data="{}",
        merged_profile="test profile",
        last_refreshed_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    analysis = Analysis(
        id="anal-1",
        jd_text="test jd",
        profile_id="prof-1",
        created_at=datetime.now(timezone.utc),
        partial=False,
    )
    db_session.add(analysis)
    jp = JobResult(
        id="jr-1",
        analysis_id="anal-1",
        agent_name="job_parser",
        output_json=json.dumps(
            {
                "company": "Stripe",
                "required_skills": [],
                "nice_to_have": [],
                "role_type": "Eng",
                "seniority": "Senior",
            }
        ),
    )
    db_session.add(jp)
    await db_session.commit()
    return analysis


@pytest.mark.asyncio
async def test_list_contacts_requires_auth(unauthenticated_client: AsyncClient):
    r = await unauthenticated_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_contacts_empty(authed_client: AsyncClient, seeded_analysis):
    r = await authed_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_contacts_returns_sorted_by_confidence(
    authed_client: AsyncClient, db_session, seeded_analysis
):
    db_session.add(
        Contact(
            id="c1",
            analysis_id="anal-1",
            email="low@stripe.com",
            confidence=0.3,
            status="discovered",
            source="hunter",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        Contact(
            id="c2",
            analysis_id="anal-1",
            email="high@stripe.com",
            confidence=0.9,
            status="discovered",
            source="hunter",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    r = await authed_client.get("/api/contacts?analysis_id=anal-1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["email"] == "high@stripe.com"  # higher confidence first


@pytest.mark.asyncio
async def test_discover_requires_auth(unauthenticated_client: AsyncClient):
    r = await unauthenticated_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_discover_returns_contacts(authed_client: AsyncClient, seeded_analysis):
    mock_contacts = [
        Contact(
            id="c1",
            analysis_id="anal-1",
            email="alice@stripe.com",
            name="Alice Chen",
            title="EM",
            company="Stripe",
            source="hunter",
            confidence=0.9,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(return_value=mock_contacts),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["email"] == "alice@stripe.com"


@pytest.mark.asyncio
async def test_discover_503_on_unavailable(authed_client: AsyncClient, seeded_analysis):
    from backend.services.contact_discovery import ContactDiscoveryUnavailable

    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(side_effect=ContactDiscoveryUnavailable("Hunter.io down")),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_discover_422_on_domain_required(authed_client: AsyncClient, seeded_analysis):
    with patch(
        "backend.routes.contacts.discover_contacts",
        new=AsyncMock(side_effect=ValueError("domain_required")),
    ):
        r = await authed_client.post("/api/contacts/discover", json={"analysis_id": "anal-1"})

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_draft_404_on_missing_contact(authed_client: AsyncClient):
    r = await authed_client.post("/api/contacts/nonexistent/draft", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_draft_returns_subject_and_body(
    authed_client: AsyncClient, db_session, seeded_analysis
):
    db_session.add(
        Contact(
            id="c1",
            analysis_id="anal-1",
            email="alice@stripe.com",
            name="Alice",
            title="EM",
            company="Stripe",
            source="hunter",
            confidence=0.9,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    from backend.schemas import ColdEmailOutput

    mock_output = ColdEmailOutput(subject="Hi Alice", body="Dear Alice, ...")

    with patch("backend.routes.contacts.ColdEmailAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.with_tracking.return_value = instance
        instance.run = AsyncMock(return_value=mock_output)

        r = await authed_client.post("/api/contacts/c1/draft", json={})

    assert r.status_code == 200
    data = r.json()
    assert data["subject"] == "Hi Alice"
    assert data["body"] == "Dear Alice, ..."


@pytest.mark.asyncio
async def test_draft_500_on_agent_failure(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(
        Contact(
            id="c2",
            analysis_id="anal-1",
            email="bob@stripe.com",
            source="hunter",
            confidence=0.5,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    from backend.agents.job_parser import AgentError

    with patch("backend.routes.contacts.ColdEmailAgent") as MockAgent:
        instance = MockAgent.return_value
        instance.with_tracking.return_value = instance
        instance.run = AsyncMock(side_effect=AgentError("bad json"))

        r = await authed_client.post("/api/contacts/c2/draft", json={})

    assert r.status_code == 500


@pytest.mark.asyncio
async def test_send_400_when_no_draft(authed_client: AsyncClient, db_session, seeded_analysis):
    db_session.add(
        Contact(
            id="c3",
            analysis_id="anal-1",
            email="carol@stripe.com",
            source="hunter",
            confidence=0.6,
            status="discovered",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    r = await authed_client.post("/api/contacts/c3/send", json={})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_send_idempotent_when_already_sent(
    authed_client: AsyncClient, db_session, seeded_analysis
):
    db_session.add(
        Contact(
            id="c4",
            analysis_id="anal-1",
            email="dave@stripe.com",
            source="hunter",
            confidence=0.7,
            status="sent",
            draft_text="Hello Dave",
            sent_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    r = await authed_client.post("/api/contacts/c4/send", json={})
    assert r.status_code == 200
    assert r.json()["sent"] is True
