"""Deterministic faithfulness checks for the chat editor (design §9, option (a)).

Flag-only and NON-mutating: unlike validate_resume_tailorer (which omits unsupported
items — correct for the automated tailorer), the chat path surfaces warnings and lets
the user keep, dismiss, or undo. The user is the ground truth for their own resume.
Zero LLM calls.

Deliberately UNCHECKED at this layer: job titles, dates, degrees, and project names.
Literal matching would false-positive on nearly every legitimate rephrasing ("SWE II"
to "Software Engineer", "2022-2024" to "Mar 2022 - Present"). Those claim types are
covered by the grounding prompt (Layer 1) with the optional LLM judge (Layer 3,
resume_faithfulness_judge_enabled) in reserve — see design spec §9.
"""

from __future__ import annotations

import re

from backend.evals.validators import _evidence_text, _literal_present, _skill_present, _warn
from backend.schemas import ResumeTailorerOutput, ValidationWarning

_AGENT = "resume_editor"
# Digit runs (optionally decimal / percent) — "40", "3.5", "87%".
_METRIC_RE = re.compile(r"\d+(?:\.\d+)?%?")
_DASHES = ("—", "–")  # em dash, en dash


def _prose_fields(content: ResumeTailorerOutput) -> list[str]:
    parts: list[str] = [content.headline, content.summary]
    for exp in content.experience:
        parts.extend(exp.bullets)
    for proj in content.projects:
        if proj.description:
            parts.append(proj.description)
        parts.extend(proj.bullets)
    return [p for p in parts if p]


def _check_metrics(cv_text: str, content: ResumeTailorerOutput) -> list[ValidationWarning]:
    """A number the profile never mentions is the classic resume hallucination.
    Literal digit-string match: '40%' is supported by '40' anywhere in the source;
    'forty percent' in the source does NOT support '40%'. Digit-boundary guarded so a
    fabricated '40%' is not wrongly "supported" by an unrelated longer number in the
    source (e.g. '140') — the match must not be adjacent to another digit on either
    side. Known limitation: comma-grouped numbers ('1,200') tokenize as separate runs
    ('1', '200') and may warn even when the source has the ungrouped form; dismiss the
    chip. Deterministic > clever."""
    warnings: list[ValidationWarning] = []
    for text in _prose_fields(content):
        for token in _METRIC_RE.findall(text):
            bare = token.rstrip("%")
            if bare and re.search(rf"(?<!\d){re.escape(bare)}(?!\d)", cv_text) is None:
                warnings.append(
                    _warn(
                        _AGENT,
                        "unsupported_metric",
                        f"'{token}' (in: '{text[:60]}') was not found in your profile, "
                        "verify before keeping",
                    )
                )
    return warnings


def validate_resume_faithfulness(
    content: ResumeTailorerOutput, source_text: str | None
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []

    # Style: no em/en dashes, ever (runs even without a source).
    for text in _prose_fields(content):
        if any(d in text for d in _DASHES):
            warnings.append(
                _warn(_AGENT, "style_dash", f"em/en dash in: '{text[:60]}', rephrase or use commas")
            )

    cv_text = _evidence_text(source_text)
    if not cv_text:
        return warnings  # no source to ground against; skip grounding checks

    for exp in content.experience:
        if exp.company and not _literal_present(cv_text, exp.company):
            warnings.append(
                _warn(
                    _AGENT,
                    "unsupported_employer",
                    f"employer '{exp.company}' was not found in your profile, "
                    "verify before keeping",
                )
            )
    for edu in content.education:
        if edu.institution and not _literal_present(cv_text, edu.institution):
            warnings.append(
                _warn(
                    _AGENT,
                    "unsupported_institution",
                    f"institution '{edu.institution}' was not found in your profile, "
                    "verify before keeping",
                )
            )
    for skill in content.skills:
        if not _skill_present(cv_text, skill):
            warnings.append(
                _warn(
                    _AGENT,
                    "unsupported_skill",
                    f"skill '{skill}' was not found in your profile, verify before keeping",
                )
            )

    warnings.extend(_check_metrics(cv_text, content))
    return warnings
