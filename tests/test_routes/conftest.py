from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _stub_profile_extractor():
    """Default-stub the resume->YAML extractor so uploads never make a live LLM
    call. Tests that need specific extracted output patch ProfileExtractorAgent.run
    themselves; that inner patch overrides this default for the duration of the test."""
    from unittest.mock import AsyncMock, patch

    from backend.schemas import ExtractedProfile

    with patch(
        "backend.agents.profile_extractor.ProfileExtractorAgent.run",
        new_callable=AsyncMock,
        return_value=ExtractedProfile(),
    ):
        yield
