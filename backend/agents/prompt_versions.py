from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptVersion:
    agent_name: str
    model: str
    prompt_name: str
    prompt_path: str
    prompt_hash: str
    prompt_version: str

    def model_dump(self) -> dict[str, str]:
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "prompt_name": self.prompt_name,
            "prompt_path": self.prompt_path,
            "prompt_hash": self.prompt_hash,
            "prompt_version": self.prompt_version,
        }


def compute_prompt_hash(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def build_prompt_version(
    *,
    agent_name: str,
    model: str,
    prompt_name: str,
    prompt_path: str | Path,
    prompt_text: str,
) -> PromptVersion:
    prompt_hash = compute_prompt_hash(prompt_text)
    return PromptVersion(
        agent_name=agent_name,
        model=model,
        prompt_name=prompt_name,
        prompt_path=str(prompt_path),
        prompt_hash=prompt_hash,
        prompt_version=f"sha256:{prompt_hash[:12]}",
    )
