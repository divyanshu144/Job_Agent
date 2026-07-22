from __future__ import annotations

import json

import anthropic
import httpx

import backend.models  # noqa: F401
from backend.services import resume_chat
from tests.factories import make_profile

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

        # commit through the real service so rev advances:
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
