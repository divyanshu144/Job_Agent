# Resume Editor — Plan 3: Faithfulness Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic, zero-LLM faithfulness checking for chat edits — flag fabricated employers, institutions, skills, and metrics (plus em/en dashes) against the profile source text, surface the flags in the chat result (design §9; **option (a): commit + dismissible flag** — flags never block or mutate the edit).

**Architecture:** A new `backend/evals/faithfulness.py` module with one pure function, `validate_resume_faithfulness(content, source_text)`, reusing the existing helpers in `backend/evals/validators.py` (`_literal_present`, `_skill_present`, `_evidence_text`). Unlike `validate_resume_tailorer` (which *mutates* output, omitting unsupported items — right for the automated tailorer), this validator is **non-mutating and flag-only**: the user is the ground truth for their own resume, so the chat path warns and lets them keep/dismiss/undo. `resume_chat.apply_chat_edit` runs it against the same grounding corpus the agent saw (`profile_ctx` from `build_resume_tailoring_context`) and returns the warnings in `ResumeChatResult.warnings` (the seam Plan 2 wired empty). The edit commits regardless — a flagged edit is one `undo` away from reverted.

**Tech Stack:** Python 3.11 · Pydantic v2 · pytest. No LLM calls anywhere in this plan (the optional judge stays behind `resume_faithfulness_judge_enabled=False`, untouched).

## Global Constraints

- **Option (a) semantics:** validation NEVER blocks or mutates the edit. `apply_chat_edit` commits exactly as today; warnings ride along in the result. No pending state, no confirmation round-trip.
- The validator is **non-mutating**: it must not modify `content` (no `_append_omission`, no field-stripping — those belong to the tailorer path only).
- Reuse, don't duplicate: import `_evidence_text`, `_literal_present`, `_skill_present`, and `_warn` from `backend.evals.validators` (they are module-level functions; importing private-prefixed helpers within the same package is the established pattern — `validators.py` is the only other module in `backend/evals/` with these).
- Warnings use the existing `ValidationWarning` shape via `_warn(agent, rule, detail, severity=...)` with `agent="resume_editor"` and `severity="warn"` (never `"error"` — nothing here blocks).
- `ResumeChatResult.warnings` is a REAL response field (already so in Plan 2) — distinct from the `exclude=True` meta-field convention on agent outputs, which is unchanged (`ResumeTailorerOutput.validation_warnings` stays excluded; it never enters prompts).
- If the source text is empty (`_evidence_text` returns `""`), grounding checks are skipped (no source to check against — mirrors `validate_resume_tailorer`); the dash check still runs.
- Known limitation (accepted, documented in code): the metric check matches digit strings literally — "40%" in content is supported by "40" anywhere in the source; "forty percent" in the source does NOT support "40%". Deterministic beats clever here.
- `make check` green; every behavior change test-covered. Tests: `tests/test_evals/test_faithfulness.py` (exists as a directory package), plus additions to `tests/test_services/test_resume_chat.py` and `tests/test_routes/test_resume_chat.py`.

---

### Task 1: `validate_resume_faithfulness` + unit tests

**Files:**
- Create: `backend/evals/faithfulness.py`
- Test: `tests/test_evals/test_faithfulness.py`

**Interfaces:**
- Consumes: `ResumeTailorerOutput`, `ValidationWarning` (schemas); `_evidence_text`, `_literal_present`, `_skill_present`, `_warn` (from `backend.evals.validators`).
- Produces: `validate_resume_faithfulness(content: ResumeTailorerOutput, source_text: str | None) -> list[ValidationWarning]` — pure, non-mutating. Rules emitted: `unsupported_employer`, `unsupported_institution`, `unsupported_skill`, `unsupported_metric`, `style_dash`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evals/test_faithfulness.py
from __future__ import annotations

import json

from backend.evals.faithfulness import validate_resume_faithfulness
from backend.schemas import ResumeTailorerOutput

_SOURCE = """
## Candidate Profile (YAML)
Worked at Acme Corp as a Software Engineer, 2022-2024.
Built the billing pipeline; cut p99 latency by 40 percent (40%).
Skills: Python, FastAPI, PostgreSQL.
BSc Computer Science, PES University, 2017-2021.
"""


def _content(**overrides) -> ResumeTailorerOutput:
    base = {
        "headline": "Software Engineer",
        "summary": "Engineer with Python experience.",
        "skills": ["Python"],
        "experience": [
            {"company": "Acme Corp", "role": "Software Engineer", "dates": "2022-2024",
             "bullets": ["Built the billing pipeline"]}
        ],
        "education": [{"institution": "PES University", "degree": "BSc", "dates": "2017-2021"}],
    }
    base.update(overrides)
    return ResumeTailorerOutput.model_validate(base)


def test_grounded_content_yields_no_warnings():
    assert validate_resume_faithfulness(_content(), _SOURCE) == []


def test_fabricated_employer_flagged():
    content = _content(experience=[{"company": "Google", "role": "SWE", "bullets": []}])
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_employer" in rules


def test_fabricated_institution_flagged():
    content = _content(education=[{"institution": "MIT", "degree": "BSc"}])
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_institution" in rules


def test_fabricated_skill_flagged_but_content_not_mutated():
    content = _content(skills=["Python", "Kubernetes"])
    warnings = validate_resume_faithfulness(content, _SOURCE)
    assert "unsupported_skill" in [w.rule for w in warnings]
    assert content.skills == ["Python", "Kubernetes"]  # NON-mutating: nothing stripped


def test_fabricated_metric_flagged():
    content = _content(
        experience=[{"company": "Acme Corp", "role": "SWE",
                     "bullets": ["Improved throughput by 87%"]}]
    )
    rules = [w.rule for w in validate_resume_faithfulness(content, _SOURCE)]
    assert "unsupported_metric" in rules


def test_supported_metric_not_flagged():
    content = _content(
        experience=[{"company": "Acme Corp", "role": "SWE",
                     "bullets": ["Cut p99 latency by 40%"]}]
    )
    assert [w for w in validate_resume_faithfulness(content, _SOURCE)
            if w.rule == "unsupported_metric"] == []


def test_dash_flagged_even_without_source():
    content = _content(summary="Engineer — loves Python")
    rules = [w.rule for w in validate_resume_faithfulness(content, None)]
    assert rules == ["style_dash"]  # dash check runs; grounding checks skipped (no source)


def test_empty_source_skips_grounding_checks():
    content = _content(skills=["Kubernetes"], experience=[{"company": "Google", "bullets": []}])
    assert validate_resume_faithfulness(content, "") == []


def test_all_warnings_are_warn_severity_from_resume_editor():
    content = _content(skills=["Kubernetes"], summary="dash — here")
    for w in validate_resume_faithfulness(content, _SOURCE):
        assert w.agent == "resume_editor" and w.severity == "warn"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_evals/test_faithfulness.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.evals.faithfulness`.

- [ ] **Step 3: Implement the validator**

```python
# backend/evals/faithfulness.py
"""Deterministic faithfulness checks for the chat editor (design §9, option (a)).

Flag-only and NON-mutating: unlike validate_resume_tailorer (which omits unsupported
items — correct for the automated tailorer), the chat path surfaces warnings and lets
the user keep, dismiss, or undo. The user is the ground truth for their own resume.
Zero LLM calls.
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
    'forty percent' in the source does NOT support '40%'. Deterministic > clever."""
    warnings: list[ValidationWarning] = []
    for text in _prose_fields(content):
        for token in _METRIC_RE.findall(text):
            bare = token.rstrip("%")
            if bare and bare not in cv_text:
                warnings.append(
                    _warn(
                        _AGENT,
                        "unsupported_metric",
                        f"'{token}' (in: '{text[:60]}') was not found in your profile — "
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
                _warn(_AGENT, "style_dash", f"em/en dash in: '{text[:60]}' — rephrase or use commas")
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
                    f"employer '{exp.company}' was not found in your profile — verify before keeping",
                )
            )
    for edu in content.education:
        if edu.institution and not _literal_present(cv_text, edu.institution):
            warnings.append(
                _warn(
                    _AGENT,
                    "unsupported_institution",
                    f"institution '{edu.institution}' was not found in your profile — "
                    "verify before keeping",
                )
            )
    for skill in content.skills:
        if not _skill_present(cv_text, skill):
            warnings.append(
                _warn(
                    _AGENT,
                    "unsupported_skill",
                    f"skill '{skill}' was not found in your profile — verify before keeping",
                )
            )

    warnings.extend(_check_metrics(cv_text, content))
    return warnings
```

Note for the implementer: `_warn`'s exact signature is in `backend/evals/validators.py:72` — confirm the parameter order/names before writing (the plan assumes `_warn(agent, rule, detail, severity="warn")` with `"warn"` as the default; if the default differs, pass `severity="warn"` explicitly).

Check `_evidence_text`'s behavior at `validators.py:110` — if it lowercases the text, the metric check's `bare not in cv_text` comparison is against lowercased text (digits unaffected — fine); keep the implementation consistent with whatever it returns.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_evals/test_faithfulness.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Lint gate + commit**

Run: `make fmt && make lint`
Expected: clean (ruff + mypy + schema-drift).

```bash
git add backend/evals/faithfulness.py tests/test_evals/test_faithfulness.py
git commit -m "feat(resume-editor): deterministic faithfulness validator (flag-only, no LLM)"
```

---

### Task 2: Wire warnings into the chat edit path

**Files:**
- Modify: `backend/services/resume_chat.py` (populate `warnings`)
- Test: `tests/test_services/test_resume_chat.py` (append), `tests/test_routes/test_resume_chat.py` (append)

**Interfaces:**
- Consumes: `validate_resume_faithfulness` (Task 1); the existing `apply_chat_edit` flow and `profile_ctx`.
- Produces: `ResumeChatResult.warnings` populated from the validator, computed against the same `profile_ctx` the agent was grounded on. Commit behavior unchanged (option (a)).

- [ ] **Step 1: Write the failing service test**

Append to `tests/test_services/test_resume_chat.py`:

```python
async def test_chat_edit_flags_fabrications_but_still_commits(db_session):
    """Option (a): a flagged edit COMMITS (rev advances) and carries warnings —
    it is never blocked; the user dismisses or undoes."""
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    out = ResumeEditorOutput.model_validate(
        {
            "content": {
                "headline": "Engineer",
                "skills": ["Python"],
                "experience": [
                    {"company": "Globex", "role": "SWE", "bullets": ["Raised revenue 300%"]}
                ],
            },
            "summary": "big claims",
        }
    )
    result = await resume_chat.apply_chat_edit(
        db_session, doc, user.id, base_rev=0, instruction="beef it up",
        agent_factory=_fake_agent(out),
    )
    assert result.rev == 1  # committed regardless — option (a)
    rules = [w.rule for w in result.warnings]
    assert "unsupported_employer" in rules
    assert "unsupported_metric" in rules


async def test_chat_edit_grounded_output_has_no_warnings(db_session):
    user = await make_user(db_session)
    doc = await _seed_master(db_session, user.id)
    # _seed_master's profile has yaml_data="Python, FastAPI" — stay inside it.
    out = ResumeEditorOutput.model_validate(
        {"content": {"headline": "Engineer", "skills": ["Python"]}, "summary": "ok"}
    )
    result = await resume_chat.apply_chat_edit(
        db_session, doc, user.id, base_rev=0, instruction="tidy",
        agent_factory=_fake_agent(out),
    )
    assert result.warnings == []
```

- [ ] **Step 2: Run to verify the first test fails**

Run: `pytest tests/test_services/test_resume_chat.py -k flags_fabrications -v`
Expected: FAIL — `result.warnings` is `[]` (Plan 2 stub).

- [ ] **Step 3: Wire the validator into `apply_chat_edit`**

In `backend/services/resume_chat.py`: add the import and replace the `warnings=[]` stub.

```python
from backend.evals.faithfulness import validate_resume_faithfulness
```

In `apply_chat_edit`, after the `apply_write` call (the edit commits first — option (a)), compute the warnings against the same grounding corpus the agent saw, and pass them into the result:

```python
    # Option (a): flag, never block. Computed against the same profile corpus the
    # agent was grounded on, AFTER the commit — a flagged edit is one undo away.
    warnings = validate_resume_faithfulness(output.content, profile_ctx)
```

and in the returned `ResumeChatResult`, replace `warnings=[],  # Plan 3 populates...` with `warnings=warnings,`.

- [ ] **Step 4: Run the service tests**

Run: `pytest tests/test_services/test_resume_chat.py -v`
Expected: PASS (both new tests; all prior tests unchanged — note `test_chat_edit_commits_via_cas_and_bumps_rev` uses headline "Senior Backend Engineer" against a profile of "Python, FastAPI": headline/summary are prose with no digits and no entity fields, so it produces no warnings and stays green. If any pre-existing test trips a warning assertion it does not make, that's fine — they don't assert on `warnings`).

- [ ] **Step 5: Write the failing route test (warnings reach the SSE payload)**

Append to `tests/test_routes/test_resume_chat.py`:

```python
async def test_edit_done_carries_warnings(app_client, db_session, monkeypatch):
    doc = await _seed(app_client, db_session)

    async def _fake_edit(db, d, user_id, base_rev, instruction, **kw):
        from backend.schemas import ResumeChatResult, ResumeTailorerOutput, ValidationWarning

        return ResumeChatResult(
            rev=base_rev + 1,
            content=ResumeTailorerOutput(headline="X"),
            summary="s",
            warnings=[ValidationWarning(agent="resume_editor", rule="unsupported_metric",
                                        detail="'99%' not found in your profile",
                                        severity="warn")],
            new_rule=None,
        )

    monkeypatch.setattr(resume_chat, "apply_chat_edit", _fake_edit)
    resp = await app_client.post(
        f"/api/resume/{doc['id']}/chat", json={"base_rev": 0, "instruction": "x"}
    )
    done = next(d for n, d in _parse_sse(resp.text) if n == "edit_done")
    assert done["warnings"][0]["rule"] == "unsupported_metric"
```

Run: `pytest tests/test_routes/test_resume_chat.py -k warnings -v`
Expected: PASS immediately IF Plan 2's `model_dump(mode="json")` already serializes the field (it does — `warnings` is a plain field on `ResumeChatResult`). This test is a contract lock, not a change driver: if it unexpectedly fails, the serialization is broken and must be fixed.

- [ ] **Step 6: Full gate + commit**

Run: `make check`
Expected: green (fmt, ruff, mypy, schema-drift, all tests, coverage ≥70%).

```bash
git add backend/services/resume_chat.py tests/test_services/test_resume_chat.py tests/test_routes/test_resume_chat.py
git commit -m "feat(resume-editor): chat edits carry faithfulness warnings (flag-only, option a)"
```

---

## Self-Review

**Spec coverage (Plan 3 scope = design §9 Layer 2 + user-visible warnings, option (a)):**
- §9 Layer 2 deterministic validator (entities, metrics, skills; no LLM) → Task 1 ✓
- No-dash style rule → Task 1 (`style_dash`, runs sourceless) ✓
- Non-mutating / flag-only for the chat path (user is ground truth) → Task 1 (explicit non-mutation test) ✓
- Warnings reach the user (editor response, not logger-only) while `exclude=True` meta-field convention stays intact → Task 2 ✓
- Option (a): flagged edits still commit; never blocked → Task 2 (`rev == 1` + warnings assertion) ✓
- Same grounding corpus as the agent (`profile_ctx`) → Task 2 ✓
- §9 Layer 3 judge stays off (`resume_faithfulness_judge_enabled=False`) → untouched, by design ✓
- Deferred: "flagged edit never auto-promoted to master" applies to the per-analysis → master promotion route, which lands in Plan 4 (master-as-base) — the guard belongs there. Eval temptation-cases against the *live* model are not CI-runnable; the CI-runnable equivalents (fabricating stub output → flagged) are Tasks 1–2.

**Placeholder scan:** none.

**Type consistency:** `validate_resume_faithfulness(content: ResumeTailorerOutput, source_text: str | None) -> list[ValidationWarning]` matches its Task 2 call (`output.content`, `profile_ctx: str`); `_warn` usage flagged for signature confirmation at `validators.py:72`; `ResumeChatResult.warnings: list[ValidationWarning]` already exists (Plan 2).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-resume-editor-03-faithfulness.md`. Two tasks, both small. Depends on Plans 1–2 (merged). Plan 4 (master-as-base) adds the promotion-guard; Plan 5 renders the warnings UI.
