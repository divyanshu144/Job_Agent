import json
from unittest.mock import patch

import pytest
import yaml

from backend.schemas import ExtractedProfile
from backend.services.profile_builder import extracted_profile_to_yaml


def test_extracted_profile_to_yaml_roundtrips_into_schema_shape():
    profile = ExtractedProfile.model_validate(
        {
            "identity": {
                "name": "Ada Lovelace",
                "headline": "ML Engineer",
                "location": "London",
                "phone": "+44 7000 000000",
            },
            "core_skills": {
                "languages": ["Python", "SQL"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
            },
            "experience": [
                {
                    "company": "Analytical Engines",
                    "role": "Engineer",
                    "dates": "2023-2025",
                    "highlights": ["Built the first algorithm"],
                }
            ],
            "featured_projects": [{"name": "Note G", "themes": ["computation"]}],
            "education": [
                {
                    "institution": "University of London",
                    "degree": "BSc",
                    "field_of_study": "Mathematics",
                    "dates": "1840-1843",
                }
            ],
        }
    )

    text = extracted_profile_to_yaml(profile)
    loaded = yaml.safe_load(text)

    assert loaded["identity"]["name"] == "Ada Lovelace"
    assert loaded["identity"]["phone"] == "+44 7000 000000"
    assert loaded["core_skills"]["languages"] == ["Python", "SQL"]
    assert loaded["experience"][0]["company"] == "Analytical Engines"
    assert loaded["featured_projects"][0]["name"] == "Note G"
    assert loaded["education"][0]["institution"] == "University of London"
    assert loaded["education"][0]["degree"] == "BSc"
    assert "search_profiles" not in loaded


def test_extracted_profile_to_yaml_handles_empty_profile():
    text = extracted_profile_to_yaml(ExtractedProfile())
    loaded = yaml.safe_load(text)
    assert loaded["identity"]["name"] == ""
    assert loaded["core_skills"]["languages"] == []
    assert loaded["experience"] == []
    assert loaded["featured_projects"] == []
    assert loaded["education"] == []


HAPPY_EXTRACT = json.dumps(
    {
        "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
        "core_skills": {"languages": ["Python"], "frameworks": ["FastAPI"], "tools": ["Docker"]},
        "experience": [
            {"company": "Acme", "role": "Engineer", "dates": "2023", "highlights": ["Shipped X"]}
        ],
        "featured_projects": [{"name": "JobFit", "themes": ["LLM"]}],
        "education": [
            {
                "institution": "MIT",
                "degree": "MSc",
                "field_of_study": "Computer Science",
                "dates": "2019-2021",
            }
        ],
    }
)


async def test_profile_extractor_happy_path():
    from backend.agents.profile_extractor import ProfileExtractorAgent

    async def _call(self, s, u):
        return HAPPY_EXTRACT

    with patch.object(ProfileExtractorAgent, "_call", new=_call):
        result = await ProfileExtractorAgent().run("Ada Lovelace, ML Engineer, Python, FastAPI...")

    assert isinstance(result, ExtractedProfile)
    assert result.identity.name == "Ada Lovelace"
    assert result.core_skills.languages == ["Python"]
    assert result.experience[0].company == "Acme"
    assert result.education[0].institution == "MIT"
    assert result.education[0].degree == "MSc"


async def test_profile_extractor_uses_haiku():
    from backend.agents.base import HAIKU
    from backend.agents.profile_extractor import ProfileExtractorAgent

    assert ProfileExtractorAgent.model == HAIKU


@pytest.mark.parametrize("bad", ["not json", json.dumps({"identity": "wrong-type"})])
async def test_profile_extractor_malformed_raises(bad):
    from backend.agents.base import AgentError
    from backend.agents.profile_extractor import ProfileExtractorAgent

    async def _call(self, s, u):
        return bad

    with patch.object(ProfileExtractorAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ProfileExtractorAgent().run("resume text")
