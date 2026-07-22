import json

import anthropic
import httpx
import pytest

from backend.models import Profile, ResumeDocument, ResumeEditRule
from backend.schemas import ResumeEditorOutput
from backend.services import resume_chat
from backend.services import resume_document as docsvc
from tests.factories import make_user


async def _seed_master(db, user_id) -> ResumeDocument:
    profile = Profile(
        user_id=user_id,
        yaml_data="Python, FastAPI",
        cv_text="",
        merged_profile="m",
        profile_review_data="{}",
    )
    db.add(profile)
    await db.flush()
    return await docsvc.get_or_seed_master(db, user_id, profile)


def _fake_agent(output: ResumeEditorOutput, *, fail_times: int = 0, record: dict | None = None):
    # Call count is shared across every instance this factory produces (not per
    # instance): apply_chat_edit's fallback path constructs a FRESH agent instance,
    # so fail_times must count calls across instances to model "the first N calls
    # anywhere fail, then it recovers" rather than "each fresh instance's first call
    # fails" (which would make a fresh fallback unable to ever succeed).
    calls = {"n": 0}

    class _Fake:
        def __init__(self) -> None:
            self.model = "claude-opus-4-8"

        def with_tracking(self, *a, **k):
            return self

        async def run(self, current_resume, profile, rules, instruction):
            calls["n"] += 1
            if record is not None:
                record["model"] = self.model
                record["rules"] = rules
            if calls["n"] <= fail_times:
                raise anthropic.APITimeoutError(request=httpx.Request("POST", "https://x"))
            return output

    return _Fake


async def test_chat_edit_commits_via_cas_and_bumps_rev(db_session):
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    out = ResumeEditorOutput.model_validate(
        {
            "content": {"headline": "Senior Backend Engineer"},
            "summary": "Sharpened.",
            "new_rule": None,
        }
    )
    result = await resume_chat.apply_chat_edit(
        db_session,
        doc,
        user.id,
        base_rev=0,
        instruction="make it senior",
        agent_factory=_fake_agent(out),
    )
    assert result.rev == 1
    assert result.content.headline == "Senior Backend Engineer"
    assert json.loads(doc.content_json)["headline"] == "Senior Backend Engineer"


async def test_chat_edit_captures_rule(db_session):
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    out = ResumeEditorOutput.model_validate(
        {
            "content": {"headline": "X"},
            "summary": "Removed word.",
            "new_rule": {"mode": "never", "text": "utilized", "scope": "resume"},
        }
    )
    result = await resume_chat.apply_chat_edit(
        db_session,
        doc,
        user.id,
        base_rev=0,
        instruction="never say utilized",
        agent_factory=_fake_agent(out),
    )
    assert result.new_rule is not None and result.new_rule.text == "utilized"
    rows = (
        (
            await db_session.execute(
                __import__("sqlalchemy")
                .select(ResumeEditRule)
                .where(ResumeEditRule.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].text == "utilized"


async def test_chat_edit_falls_back_to_sonnet_on_persistent_failure(db_session):
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    out = ResumeEditorOutput.model_validate({"content": {"headline": "OK"}, "summary": "ok"})
    record: dict = {}
    # First factory instance fails (Opus), second (fallback) succeeds — apply_chat_edit
    # constructs a fresh agent for the fallback with the fallback model.
    result = await resume_chat.apply_chat_edit(
        db_session,
        doc,
        user.id,
        base_rev=0,
        instruction="edit",
        agent_factory=_fake_agent(out, fail_times=1, record=record),
    )
    assert result.rev == 1
    assert record["model"] == "claude-sonnet-4-6"  # the fallback agent ran


async def test_chat_edit_stale_base_rev_raises(db_session):
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    out = ResumeEditorOutput.model_validate({"content": {"headline": "A"}, "summary": "a"})
    await resume_chat.apply_chat_edit(
        db_session, doc, user.id, base_rev=0, instruction="e", agent_factory=_fake_agent(out)
    )
    with pytest.raises(docsvc.StaleRevError):
        await resume_chat.apply_chat_edit(
            db_session, doc, user.id, base_rev=0, instruction="e2", agent_factory=_fake_agent(out)
        )
