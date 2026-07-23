import pytest
from pydantic import ValidationError

from backend.schemas import (
    EditRuleCreate,
    ResumeChatRequest,
    ResumeContentUpdate,
    ResumeDocumentResponse,
    ResumeEditorOutput,
    ResumeTailorerOutput,
)


def test_chat_request_rejects_empty_instruction_and_negative_rev():
    with pytest.raises(ValidationError):
        ResumeChatRequest(base_rev=0, instruction="")
    with pytest.raises(ValidationError):
        ResumeChatRequest(base_rev=-1, instruction="x")


def test_content_update_requires_base_rev():
    upd = ResumeContentUpdate(base_rev=3, content=ResumeTailorerOutput(headline="Eng"))
    assert upd.base_rev == 3
    assert upd.content.headline == "Eng"


def test_document_response_carries_rev_and_content():
    resp = ResumeDocumentResponse(
        id="d1",
        kind="master",
        name="Default",
        is_active=True,
        rev=2,
        content=ResumeTailorerOutput(headline="Eng"),
        updated_at="2026-07-22T00:00:00Z",
    )
    assert resp.rev == 2 and resp.content.headline == "Eng"


def test_editor_output_parses_with_rule():
    out = ResumeEditorOutput.model_validate(
        {
            "content": {"headline": "Engineer"},
            "summary": "Tightened the first bullet.",
            "new_rule": {"mode": "never", "text": "utilized", "scope": "resume"},
        }
    )
    assert out.content.headline == "Engineer"
    assert out.summary.startswith("Tightened")
    assert isinstance(out.new_rule, EditRuleCreate) and out.new_rule.mode == "never"


def test_editor_output_rule_optional():
    out = ResumeEditorOutput.model_validate({"content": {"headline": "X"}, "summary": "no rule"})
    assert out.new_rule is None


def test_chat_request_requires_base_rev_and_instruction():
    req = ResumeChatRequest(base_rev=2, instruction="make the first bullet punchier")
    assert req.base_rev == 2 and "punchier" in req.instruction
