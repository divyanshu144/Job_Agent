from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.services.stage2 import (
    Stage2Result,
    build_stage2_system_prompt,
    parse_stage2_result,
    stage2_prompt_version,
)


def test_parse_stage2_result_valid_json_with_surrounding_text():
    result = parse_stage2_result(
        'Here is JSON: {"relevant": true, "reason": "fit", '
        '"title": "Python Engineer", "company": "Acme", "location": "Remote"}'
    )

    assert isinstance(result, Stage2Result)
    assert result.relevant is True
    assert result.reason == "fit"
    assert result.title == "Python Engineer"
    assert result.company == "Acme"
    assert result.location == "Remote"


def test_parse_stage2_result_malformed_json_raises():
    with pytest.raises(ValueError, match="No JSON object"):
        parse_stage2_result("not json")


def test_parse_stage2_result_missing_required_relevant_raises():
    with pytest.raises(ValidationError):
        parse_stage2_result('{"reason": "missing relevant"}')


def test_parse_stage2_result_ignores_extra_fields():
    result = parse_stage2_result(
        '{"relevant": false, "reason": "no", "title": "", "company": "", '
        '"location": null, "confidence": 0.2, "tags": ["sales"]}'
    )

    assert result.relevant is False
    assert not hasattr(result, "confidence")


def test_stage2_prompt_version_is_stable_and_identifies_prompt():
    first = stage2_prompt_version()
    second = stage2_prompt_version()

    assert first.prompt_hash == second.prompt_hash
    assert first.agent_name == "discovery_stage2"
    assert first.prompt_name == "discovery_stage2"
    assert first.model.startswith("claude-")
    assert first.prompt_version.startswith("sha256:")


def test_build_stage2_system_prompt_truncates_profile():
    prompt = build_stage2_system_prompt("a" * 1200)

    assert "a" * 1000 in prompt
    assert "a" * 1001 not in prompt


async def test_discovery_stage2_check_uses_shared_parser_and_prompt_metadata():
    from backend.services.discovery import _stage2_check

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.cache_creation_input_tokens = 0
    mock_usage.cache_read_input_tokens = 0

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage
    mock_msg.content = [
        MagicMock(
            text='{"relevant": true, "reason": "fit", "title": "Backend Engineer", '
            '"company": "Acme", "location": "London"}'
        )
    ]

    with patch(
        "backend.services.discovery.tracked_call",
        new_callable=AsyncMock,
        return_value=mock_msg,
    ) as tracked:
        result = await _stage2_check("Backend Python role", "Python FastAPI profile")

    assert result.relevant is True
    assert result.title == "Backend Engineer"
    call_kwargs = tracked.await_args.kwargs
    assert call_kwargs["prompt_name"] == "discovery_stage2"
    assert len(call_kwargs["prompt_hash"]) == 64
    assert call_kwargs["prompt_version"].startswith("sha256:")
