# Resume Editor — Design Spec

**Date:** 2026-07-22
**Status:** Draft for review
**Author:** brainstormed with the team

---

## 1. Summary

Today a tailored resume is a transient artifact: `ResumeTailorerOutput` JSON stored on a
`JobResult` row, re-rendered to DOCX/PDF on every download, and not editable after
generation. This feature makes the resume a first-class, **editable, versioned** document
with **two edit paths** (direct inline edits + a chat editor), rendered into **one locked,
ATS-friendly format for every user**, and surfaced through **two entry points** (a standalone
Resume section and the existing per-analysis flow) that share a single editor component.

The resume-generation and chat-edit paths run on **Claude Opus 4.8** (`claude-opus-4-8`).
Truthfulness (no fabricated experience, titles, metrics, or skills) is a first-class concern
enforced by grounded prompts, a deterministic faithfulness validator, user-visible warnings,
and a "no silent save-to-master" rule.

Non-goals: template switching, font/size/alignment controls (the format is intentionally
locked), multi-column or graphical resume styles, and any open-ended agentic "loop"
behaviour.

---

## 2. Goals & constraints

- **One locked, ATS-friendly format** applied to every user. Only content varies, never layout.
- **Two edit paths:** direct inline editing (no LLM) and chat-driven editing (Opus 4.8).
- **Two entry points, one editor:** a standalone Resume section (master resume) and the
  per-analysis tailored resume, both driven by the same editor component and data model.
- **Master-as-base:** the master resume is the canonical base; a per-analysis resume is an
  editable, JD-tuned fork of it. The **full profile** (YAML + CV + semantic memory) remains
  the knowledge base — the master is a curated view, not a cage.
- **Versioning** like tsenta: a "Default" version plus create/switch/rename/delete.
- **`always`/`never` rules** remembered per user and applied to every future edit and to
  tailoring.
- **Truthfulness:** every claim traceable to the profile knowledge base.
- **Simplicity first / minimal impact:** reuse existing agents, validators, rendering,
  cost tracking, and the SSE protocol. No new cost plumbing. No open-ended loops.

---

## 3. Data model

### 3.1 `resume_documents` (new table)

An editable, versioned resume. Rows-as-versions.

| field | type | purpose |
|---|---|---|
| `id` | str PK (uuid) | |
| `user_id` | str FK → users.id | owner |
| `kind` | str | `"master"` or `"analysis"` |
| `analysis_id` | str FK → analyses.id, nullable | set when `kind="analysis"` |
| `name` | str | version name — `"Default"`, `"Aggressive"`, … |
| `content_json` | Text | structured resume content (`ResumeTailorerOutput` shape) |
| `is_active` | bool | which version is currently selected within its group |
| `created_at` / `updated_at` | datetime | |

**Version groups.**
- Master group = (`user_id`, `kind="master"`).
- Analysis group = (`analysis_id`).

A "version" is another row in the same group. Create / switch / rename / delete are row
operations. Exactly one row per group has `is_active=true` (enforced in the service layer on
switch). Deleting the active version promotes the most-recently-updated remaining row; a
group is never left with zero active rows unless the whole group is deleted.

**Seeding the master.** Seeded once, **deterministically**, from the user's profile
(`ProfileReviewData` → `ResumeTailorerOutput` shape) — no LLM cost, predictable output —
on first visit to the Resume section (lazy create). Editable immediately after.

**Per-analysis creation.** Created when `resume_tailorer` runs (see §7). The tailored output
becomes the first `kind="analysis"` row for that analysis. Edits stay on that fork; only an
explicit "Save to master" action writes back to the master group (creates/updates a master
version).

### 3.2 `resume_edit_rules` (new table)

The `always`/`never` memory. User-scoped (rules apply everywhere, like tsenta).

| field | type | purpose |
|---|---|---|
| `id` | str PK (uuid) | |
| `user_id` | str FK → users.id | owner |
| `mode` | str | `"always"` or `"never"` |
| `text` | str | e.g. "never use the word 'utilized'" |
| `scope` | str | `"resume"` / `"cover_letter"` / `"both"` |
| `created_at` | datetime | |

Injected into the `ResumeEditorAgent` prompt and the `resume_tailorer` prompt so tailoring
also respects standing rules.

### 3.3 Cover letter

The Resume/Cover-letter toggle keeps the cover letter editable in the same editor. Cover
letter content (`CoverLetterOutput`: `subject`, `body`, `tone_notes`) is stored in a parallel
`cover_letter_documents` table with the same `kind`/`analysis_id`/`name`/`is_active`/versioning
shape. Direct editing = plain text fields (subject/body). Chat editing = the same
`ResumeEditorAgent` invoked in a `cover_letter` mode (different content schema, same grounding
+ rules + resilience). Rules with `scope in ("cover_letter","both")` apply.

### 3.4 Migration

One Alembic migration adds `resume_documents`, `cover_letter_documents`, and
`resume_edit_rules`. No changes to `JobResult` (the generated tailorer output still lands there
first; the per-analysis `ResumeDocument` is created from it).

---

## 4. Model selection & config

- `resume_tailorer` and the new `ResumeEditorAgent` run on **Opus 4.8** (`claude-opus-4-8`) —
  strongest Opus tier, warmer/clearer prose (fits the "humanized content, no dashes" rule).
- Bulk discovery scoring stays on **Haiku** (unchanged).
- New settings in `config.py` (never read env outside config):
  - `resume_model: str = "claude-opus-4-8"`
  - `resume_model_fallback: str = "claude-sonnet-4-6"`
  - `resume_faithfulness_judge_enabled: bool = False` (Layer-3 LLM judge, off by default)
- Cost is already gated by `usage.py` per-user caps and logged via `tracked_call` →
  `LLMCall` → Prometheus. No new cost plumbing; Opus spend appears in the Costs dashboard
  automatically.

---

## 5. Edit paths

### 5.1 Direct editing (no LLM)

The React preview renders `content_json` in the locked ATS layout; each field/bullet is
click-to-edit inline. On blur, the frontend `PATCH`es the updated `content_json`. Pure
state → save; instant; no cost. The structured shape is field-addressable, so "edit the
second bullet of the first job" is mutating `experience[0].bullets[1]`.

### 5.2 Chat editing (Opus 4.8) — `ResumeEditorAgent` (8th agent)

Route-driven **leaf agent** using manual `template.replace(...)` slots (per the
`_inject()`-vs-`.replace()` convention — it does not consume structured `PriorOutputs`).

**Inputs:**
- current `content_json` (what the user sees now),
- compact profile context (so it can surface a relevant bullet/project not currently on the
  resume — the full profile is the knowledge base),
- the user's instruction,
- active `always`/`never` rules.

**Output (structured, re-validated against the content schema):**
- the **full updated resume content** (full-document rewrite, not a diff — simplest and safest;
  the resume is small so token cost is trivial),
- a one-line **change summary** shown in the chat thread,
- an optional **`new_rule: {mode, text, scope}`** field — emitted when the agent recognizes an
  "always/never" standing-preference intent (no brittle keyword parsing), which creates a
  `resume_edit_rules` row.

Streams over SSE so edits feel live.

**Transactional commit:** `content_json` is written **only if the new output validates** against
the Pydantic model. On failure the document is untouched.

---

## 6. Rendering & the locked ATS format

There are three renderers of the same content: the new **React HTML preview**, the **DOCX**
(`resume_docx.py`), and the **PDF** (`resume_latex_template.py` — the existing ATS-verified
LaTeX template, which *is* the locked format).

**Approach (chosen): single content model, three renderers, a contract test.**
- The HTML preview is presentation-only and matches the LaTeX template's structure/spacing as
  closely as practical.
- The **PDF remains the source of truth** for "what you download."
- A **contract test** renders a fixed `ResumeDocument` fixture through all three renderers and
  asserts **content parity** (sections present, ordering, text). Layout won't be pixel-identical
  across HTML/LaTeX, but content parity is guaranteed and tested — preventing the worst bug
  (a downloaded PDF that doesn't match the edited screen).

Rejected alternative: server-rendering the PDF on every keystroke (truest fidelity but slow,
chatty, and kills the snappy inline-edit feel).

---

## 7. Master-as-base tailoring

When an analysis runs, `resume_tailorer` receives the user's **master resume content** as the
structural base (new prompt slot), **plus** the full profile context (unchanged) so it can
still surface relevant items not on the master. Its tailored output:
1. lands on the `JobResult` row as today, and
2. becomes the first `kind="analysis"` `ResumeDocument` (an editable JD-tuned fork).

Edits to the per-analysis fork stay on the fork. "Save to master" is the only path that writes
back to the master group.

This also yields a **graceful degradation**: if tailoring fails, the per-analysis resume falls
back to the unedited master resume — still usable, just not JD-tuned.

---

## 8. Resilience (bounded, not a loop)

Layered, cheapest first. No `task_budget`, no open-ended iteration — a resume edit is a single
well-scoped rewrite.

| Layer | Mechanism |
|---|---|
| 1 — transient errors (429/5xx/overloaded/connection) | existing `BaseAgent` retry + circuit breaker; SDK auto-retry. No new code. |
| 2 — malformed output (schema-validation failure) | **one** self-correction retry (re-prompt with the validation error), reusing the `resume_latex.py` pattern. Then give up gracefully. |
| 3 — model fallback | Opus 4.8 → Sonnet 4.6, **scoped down**: only on the **chat-edit path**, and only when the **circuit breaker is open** (real outage). Surfaces a subtle "applied with a backup model" note. |

**Scoping rationale.** Generation doesn't get the model fallback — master-as-base already
degrades it gracefully. The fallback lives only where the user has invested a specific
instruction and there is no other graceful path (chat edit).

| Path | transient retry | 1 self-correction | model fallback | final degradation |
|---|---|---|---|---|
| Generation | ✅ | ✅ | ❌ | falls back to master resume |
| Chat edit | ✅ | ✅ | ✅ (breaker-open only) | document unchanged + error in chat |

---

## 9. Truthfulness & evals

**Core principle — grounding.** Every claim (employer, title, date, metric, skill, achievement)
must be traceable to the profile knowledge base (YAML + CV + memory). Agents may reword,
reorder, emphasize, and select; they may never introduce a fact absent from the source. The
most dangerous case is a fabricated **metric**.

**Layer 1 — grounding prompt constraint (prevention).** Both `resume_tailorer` and
`ResumeEditorAgent` are instructed: no new named entities, no new quantified metrics, no new
skills beyond the profile; rephrasing is allowed, invention is not.

**Layer 2 — faithfulness validator (always-on, deterministic, no LLM).** Extends
`validate_resume_tailorer` in `backend/evals/validators.py`. Extract named entities, numbers/
percentages, and skills from the new content and diff against the profile source text; anything
present in output but absent from source is flagged. Zero token cost, no LLM-checking-LLM
fragility. Also enforces the **no em/en dashes** rule. Produces `validation_warnings`.

**Layer 3 — LLM-judge faithfulness pass (optional, off by default).** A second Opus call
scoring each *changed* bullet as supported / unsupported / partial. Behind
`resume_faithfulness_judge_enabled` (default `False`). Enabled only if Layer 2 proves
insufficient in practice.

**UX — flag, don't silently block.** The user is the ground truth for their own resume, so
warnings must reach the user in the editor, not just the logs. This is a deliberate,
convention-preserving departure: `validation_warnings` stays `exclude=True` (never enters
`PriorOutputs` or downstream prompts), but the **editor endpoint returns the warnings explicitly
in its API response** so the UI can show e.g. "⚠️ This edit added a metric ('40%') not found in
your profile — verify before keeping." A flagged edit is **never auto-saved to the master** —
promotion requires explicit user confirmation. Legit edits go through with a dismissible flag.

**Evaluating `ResumeEditorAgent`.** Beyond the Definition-of-Done schema test:
- **Grounding golden cases:** "make this stronger" against a fixed profile → assert no new
  entity/number/skill absent from the profile.
- **Temptation cases:** "add an impressive metric here" → assert the agent declines to invent
  or flags the addition rather than fabricating.
- **Rule adherence:** rule "never use 'utilized'" → assert absence in output.
- **Style:** assert no em/en dashes.

---

## 10. API surface

All routes under `settings.api_prefix`. New router `routes/resume.py` (resume + cover-letter
document CRUD, versions, edit); rule management can live alongside or in the same router.

**Resume documents / versions**
- `GET  /resume` — active master resume (lazily seeded from profile on first call).
- `GET  /resume/versions` — list master versions.
- `POST /resume/versions` — create a new master version (optionally cloning the active one).
- `PATCH /resume/versions/{id}` — rename, or set active.
- `DELETE /resume/versions/{id}` — delete a version.
- `PATCH /resume/{id}/content` — save direct edits (`content_json`).
- `POST /resume/{id}/chat` — chat edit (SSE); returns updated content, change summary,
  `validation_warnings`, and any captured rule.
- `GET  /analysis/{analysis_id}/resume` — active per-analysis resume (created by the tailorer).
- `POST /analysis/{analysis_id}/resume/save-to-master` — promote the fork to a master version
  (blocked/confirmed if unresolved faithfulness warnings exist).

**Downloads** — existing `history.py` routes continue to serve DOCX/PDF, now sourced from the
active `ResumeDocument` for the analysis (falling back to the `JobResult` output during
migration).

**Cover letter** — parallel routes (`/resume/cover-letter...`, `/analysis/{id}/cover-letter...`).

**Rules**
- `GET /resume/rules` · `POST /resume/rules` · `DELETE /resume/rules/{id}`.

Every new route gets an integration test covering the happy path and the auth requirement.

---

## 11. Frontend

A new **Resume** nav item (standalone master editor) plus reuse in the per-analysis Results
flow, both rendering the **same `ResumeEditor` component**:

- **Split-pane layout:** chat/edit on the left, live locked-format preview on the right.
- **Resume / Cover letter toggle.**
- **Version selector:** Default + create/switch/rename/delete.
- **Chat box** with `always`/`never` rule capture and inline change summaries.
- **Inline direct editing** on the preview (click-to-edit fields/bullets → PATCH on blur).
- **Faithfulness warnings** surfaced inline (dismissible; block auto-save-to-master).
- **Download** (existing DOCX/PDF).
- Dropped from tsenta (locked format): template switcher, font family/size, alignment,
  fit-to-one-page.

New TS types mirror the backend schemas 1:1 (schema-drift checked). The SSE chat stream reuses
the existing `EventSource` dispatcher pattern in `api/client.ts`.

---

## 12. Definition of done

- `make check` passes (fmt + lint + test).
- `ResumeEditorAgent` has a `tests/test_agents/` test validating output schema against a mocked
  `_call()`, plus the grounding/temptation/rule/style eval cases (§9).
- Faithfulness validator has unit tests (fabricated entity, fabricated metric, added skill,
  em/en dash).
- Contract test asserts HTML/DOCX/PDF content parity (§6).
- Every new route has an integration test (happy path + auth).
- Alembic migration applies cleanly.
- `HANDOFF.md`, `tasks/todo.md` updated.

---

## 13. Build sequence (for the implementation plan)

1. Migration + models (`resume_documents`, `cover_letter_documents`, `resume_edit_rules`).
2. Deterministic master seed from profile + `resume.py` document/version CRUD + tests.
3. React `ResumeEditor` shell: split pane, locked HTML preview, inline direct edit + PATCH.
4. `ResumeEditorAgent` (Opus 4.8) + chat SSE endpoint + resilience (§8).
5. Faithfulness validator (§9 Layer 2) + user-visible warnings wiring + rules capture/apply.
6. Master-as-base tailoring integration (§7) + graceful degradation.
7. Versioning UI + save-to-master (confirmation on warnings).
8. Cover-letter mode (parallel table, same editor).
9. Contract test (§6) + Costs/Sentry sanity + docs/handoff.

---

## 14. Open questions

- Cover-letter chat editing depth: full parity now, or ship resume-first and layer cover-letter
  chat in a follow-up? (Spec assumes parity; can be deferred without data-model change.)
- Optional Layer-3 LLM judge: keep off until Layer 2 shows gaps in real use.
