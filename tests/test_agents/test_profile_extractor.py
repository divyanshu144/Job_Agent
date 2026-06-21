import yaml

from backend.schemas import ExtractedProfile
from backend.services.profile_builder import extracted_profile_to_yaml


def test_extracted_profile_to_yaml_roundtrips_into_schema_shape():
    profile = ExtractedProfile.model_validate(
        {
            "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
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
        }
    )

    text = extracted_profile_to_yaml(profile)
    loaded = yaml.safe_load(text)

    assert loaded["identity"]["name"] == "Ada Lovelace"
    assert loaded["core_skills"]["languages"] == ["Python", "SQL"]
    assert loaded["experience"][0]["company"] == "Analytical Engines"
    assert loaded["featured_projects"][0]["name"] == "Note G"
    assert "search_profiles" not in loaded


def test_extracted_profile_to_yaml_handles_empty_profile():
    text = extracted_profile_to_yaml(ExtractedProfile())
    loaded = yaml.safe_load(text)
    assert loaded["identity"]["name"] == ""
    assert loaded["core_skills"]["languages"] == []
    assert loaded["experience"] == []
    assert loaded["featured_projects"] == []
