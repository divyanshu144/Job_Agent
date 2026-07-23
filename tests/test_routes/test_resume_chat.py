from __future__ import annotations

import json

import anthropic
import httpx

import backend.models  # noqa: F401
from backend.services import resume_chat
from backend.services import resume_document as docsvc
from tests.factories import make_analysis, make_profile

_USER_ID = "test-user-id"  # matches the harness's authenticated user (see test_resume.py)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name:
            events.append((name, data))
    return events


async def _seed(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}")
    await db_session.commit()
    return (await app_client.get("/api/resume")).json()


async def test_chat_streams_edit_done(app_client, db_session, monkeypatch):
    doc = await _seed(app_client, db_session)

    async def _fake_edit(db, d, user_id, base_rev, instruction, **kw):
        from backend.schemas import ResumeChatResult, ResumeTailorerOutput

        return ResumeChatResult(
            rev=base_rev + 1,
            content=ResumeTailorerOutput(headline="Edited by chat"),
            summary="did it",
            warnings=[],
            new_rule=None,
        )

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _fake_edit)

    resp = await app_client.post(
        f"/api/resume/{doc['id']}/chat",
        json={"base_rev": 0, "instruction": "make it punchy"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    names = [n for n, _ in events]
    assert names[0] == "edit_start"
    assert "edit_done" in names
    done = next(d for n, d in events if n == "edit_done")
    assert done["rev"] == 1 and done["content"]["headline"] == "Edited by chat"


async def test_chat_emits_conflict_on_stale(app_client, db_session, monkeypatch):
    doc = await _seed(app_client, db_session)
    from backend.services.resume_errors import StaleRevError

    async def _stale(db, d, user_id, base_rev, instruction, **kw):
        raise StaleRevError(current=d)

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _stale)

    resp = await app_client.post(
        f"/api/resume/{doc['id']}/chat", json={"base_rev": 0, "instruction": "x"}
    )
    assert resp.status_code == 200
    names = [n for n, _ in _parse_sse(resp.text)]
    assert "edit_conflict" in names


async def test_chat_emits_terminal_event_on_unexpected_service_error(
    app_client, db_session, monkeypatch
):
    # Simulates both the Opus primary and the Sonnet fallback exhausting their retries
    # and re-raising (e.g. anthropic.APITimeoutError) mid-stream, after edit_start has
    # already been yielded. The stream must still terminate with edit_error, not just
    # truncate silently (Task 5 review, Fix 1).
    doc = await _seed(app_client, db_session)

    async def _fake_edit(db, d, user_id, base_rev, instruction, **kw):
        raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _fake_edit)

    resp = await app_client.post(
        f"/api/resume/{doc['id']}/chat",
        json={"base_rev": 0, "instruction": "make it punchy"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    names = [n for n, _ in events]
    assert "edit_start" in names
    assert "edit_error" in names


async def test_chat_requires_auth(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/resume/whatever/chat", json={"base_rev": 0, "instruction": "x"}
    )
    assert resp.status_code == 401


async def test_edit_done_carries_warnings(app_client, db_session, monkeypatch):
    doc = await _seed(app_client, db_session)

    async def _fake_edit(db, d, user_id, base_rev, instruction, **kw):
        from backend.schemas import ResumeChatResult, ResumeTailorerOutput, ValidationWarning

        return ResumeChatResult(
            rev=base_rev + 1,
            content=ResumeTailorerOutput(headline="X"),
            summary="s",
            warnings=[
                ValidationWarning(
                    agent="resume_editor",
                    rule="unsupported_metric",
                    detail="'99%' not found in your profile",
                    severity="warn",
                )
            ],
            new_rule=None,
        )

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _fake_edit)
    resp = await app_client.post(
        f"/api/resume/{doc['id']}/chat", json={"base_rev": 0, "instruction": "x"}
    )
    done = next(d for n, d in _parse_sse(resp.text) if n == "edit_done")
    assert done["warnings"][0]["rule"] == "unsupported_metric"


async def test_chat_on_fork(app_client, db_session, monkeypatch):
    # _owned_doc has no kind filter — chat must reach per-analysis forks too, not just
    # master versions (M-2).
    analysis = await make_analysis(db_session, user_id=_USER_ID)
    fork = await docsvc.ensure_analysis_resume(
        db_session, _USER_ID, analysis.id, json.dumps({"headline": "Tailored for Acme"})
    )
    await db_session.commit()

    async def _fake_edit(db, d, user_id, base_rev, instruction, **kw):
        from backend.schemas import ResumeChatResult, ResumeTailorerOutput

        return ResumeChatResult(
            rev=base_rev + 1,
            content=ResumeTailorerOutput(headline="Edited fork by chat"),
            summary="did it",
            warnings=[],
            new_rule=None,
        )

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _fake_edit)

    resp = await app_client.post(
        f"/api/resume/{fork.id}/chat",
        json={"base_rev": 0, "instruction": "make it punchy"},
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    names = [n for n, _ in events]
    assert "edit_done" in names
    done = next(d for n, d in events if n == "edit_done")
    assert done["content"]["headline"] == "Edited fork by chat"


async def test_chat_is_ownership_scoped(app_client, db_session):
    # Another user's master doc must 404 BEFORE any streaming starts (real HTTP status).
    from backend.models import ResumeDocument
    from tests.factories import make_user

    other = await make_user(db_session, id="other-chat", email="other-chat@example.com")
    foreign = ResumeDocument(
        user_id=other.id, kind="master", name="Default", content_json="{}", is_active=True
    )
    db_session.add(foreign)
    await db_session.commit()

    resp = await app_client.post(
        f"/api/resume/{foreign.id}/chat", json={"base_rev": 0, "instruction": "x"}
    )
    assert resp.status_code == 404
