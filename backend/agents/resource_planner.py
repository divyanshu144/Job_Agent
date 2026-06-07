from __future__ import annotations

import json

from pydantic import ValidationError

from backend.agents.base import BaseAgent
from backend.agents.job_parser import AgentError, _parse_json
from backend.evals.validators import validate_resource_planner
from backend.schemas import PlannerMeta, PriorOutputs, ResourcePlannerOutput

# A gap whose resources score below this is regenerated once with a targeted prompt.
CONFIDENCE_THRESHOLD = 0.7


class ResourcePlannerAgent(BaseAgent):
    async def run(self, profile: str, jd: str, prior: PriorOutputs) -> ResourcePlannerOutput:
        # ── Pass 1: generate resources for all gaps (original behaviour) ──────────
        template = self._load_prompt("resource_planner")
        system = self._inject(template, profile, jd, prior)
        llm_calls = 0
        try:
            raw = await self._call(system, jd)
            llm_calls += 1
            output = ResourcePlannerOutput.model_validate(_parse_json(raw))
        except (json.JSONDecodeError, ValidationError, AgentError) as e:
            raise AgentError(f"resource_planner: {e}") from e

        # ── Self-check: one extra call scoring each gap's resource specificity ────
        # Degrades gracefully: an unparseable self-check is treated as "confident"
        # (no retry), so the pipeline never breaks on the meta step.
        confidences: dict[str, float] = {}
        try:
            sc_raw = await self._call(self._selfcheck_system(output), jd)
            llm_calls += 1
            confidences = self._parse_confidences(sc_raw)
        except Exception:
            confidences = {}

        low_confidence = [
            g.skill for g in output.gaps if confidences.get(g.skill, 1.0) < CONFIDENCE_THRESHOLD
        ]

        # ── Pass 2: regenerate ONLY low-confidence gaps (max 1 retry, never loops) ─
        retried: list[str] = []
        if low_confidence:
            try:
                rt_raw = await self._call(
                    self._retarget_system(profile, jd, prior, low_confidence), jd
                )
                llm_calls += 1
                regen = ResourcePlannerOutput.model_validate(_parse_json(rt_raw))
                regen_by_skill = {g.skill: g for g in regen.gaps}
                rebuilt = []
                for g in output.gaps:
                    if g.skill in low_confidence and g.skill in regen_by_skill:
                        rebuilt.append(regen_by_skill[g.skill])
                        retried.append(g.skill)
                    else:
                        rebuilt.append(g)
                output.gaps = rebuilt
            except Exception:
                pass  # keep Pass-1 resources for these gaps if regeneration fails

        output.planner_meta = PlannerMeta(
            total_llm_calls=llm_calls,
            retried_gaps=retried,
            low_confidence_gaps=low_confidence,
            gap_confidences=confidences,
        )
        output.validation_warnings = validate_resource_planner(output, prior)
        return output

    @staticmethod
    def _selfcheck_system(output: ResourcePlannerOutput) -> str:
        gaps_json = json.dumps([g.model_dump() for g in output.gaps], indent=2)
        return (
            "You are auditing a learning plan. For each gap below, score from 0.0 to 1.0 how "
            "SPECIFICALLY its resources (courses/books/projects) address that exact skill — "
            "1.0 = named, directly-relevant resources; 0.0 = vague or generic.\n\n"
            f"Gaps and their resources:\n{gaps_json}\n\n"
            "Respond with ONLY valid JSON, no preamble: "
            '{"scores": [{"skill": "<skill>", "confidence": 0.0}]}'
        )

    def _retarget_system(
        self, profile: str, jd: str, prior: PriorOutputs, skills: list[str]
    ) -> str:
        template = self._load_prompt("resource_planner")
        base = self._inject(template, profile, jd, prior)
        return (
            base
            + "\n\n## TARGETED REGENERATION\n"
            + "Your previous resources for these skills were too generic: "
            + ", ".join(skills)
            + ".\nRegenerate ONLY these skills with highly specific, named resources "
            "(exact course titles + platform, real book titles, concrete scoped projects). "
            'Output the same JSON schema containing ONLY these skills: {"gaps": [...]}'
        )

    @staticmethod
    def _parse_confidences(raw: str) -> dict[str, float]:
        data = _parse_json(raw)
        scores = data.get("scores") if isinstance(data, dict) else None
        if not isinstance(scores, list):
            return {}
        out: dict[str, float] = {}
        for item in scores:
            if isinstance(item, dict) and "skill" in item and "confidence" in item:
                try:
                    out[str(item["skill"])] = float(item["confidence"])
                except (TypeError, ValueError):
                    continue
        return out
