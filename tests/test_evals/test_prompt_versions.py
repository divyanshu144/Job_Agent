from __future__ import annotations

from backend.agents.prompt_versions import compute_prompt_hash
from backend.evals.runner import eval_prompt_versions


def test_prompt_hash_is_stable_for_same_text():
    text = "Prompt text\nwith placeholders {profile} {jd}\n"

    assert compute_prompt_hash(text) == compute_prompt_hash(text)


def test_prompt_hash_changes_when_prompt_text_changes():
    original = "You are a job parser."
    changed = "You are a careful job parser."

    assert compute_prompt_hash(original) != compute_prompt_hash(changed)


def test_eval_prompt_versions_include_agent_model_and_prompt_identity():
    versions = eval_prompt_versions()

    assert versions
    by_agent = {version.agent_name: version for version in versions}
    assert by_agent["job_parser"].model.startswith("claude-")
    assert by_agent["job_parser"].prompt_name == "job_parser"
    assert by_agent["job_parser"].prompt_path.endswith("backend/prompts/job_parser.md")
    assert len(by_agent["job_parser"].prompt_hash) == 64
    assert by_agent["job_parser"].prompt_version.startswith("sha256:")
