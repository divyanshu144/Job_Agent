from __future__ import annotations

import json
from pathlib import Path


def _container(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    return data["containerDefinitions"][0]


def test_api_worker_and_beat_have_embedding_env_and_openai_secret():
    for path in (
        "infra/aws/task-definitions/api.json",
        "infra/aws/task-definitions/worker.json",
        "infra/aws/task-definitions/beat.json",
    ):
        container = _container(path)
        env = {item["name"]: item["value"] for item in container["environment"]}
        secrets = {item["name"]: item["valueFrom"] for item in container["secrets"]}

        assert env["EMBEDDING_PROVIDER"] == "openai"
        assert env["EMBEDDING_MODEL"] == "text-embedding-3-small"
        assert env["EMBEDDING_DIMENSIONS"] == "1536"
        assert env["PGVECTOR_ENABLED"] == "true"
        assert "OPENAI_API_KEY" in secrets
        assert secrets["OPENAI_API_KEY"].endswith("/jobfit/staging/openai-api-key")
