# Session Handoff

**Updated:** 2026-07-22
**Branch:** feat/resume-editor (branched from main @ `0d9a55b`)

---

## Current State

Design/brainstorming phase for the **Resume Editor** feature. No implementation code yet —
only the design spec. Spec written and being committed:
`docs/superpowers/specs/2026-07-22-resume-editor-design.md`.

Feature (agreed with user): promote the tailored resume to a first-class **editable, versioned**
`ResumeDocument` with **two edit paths** (inline direct edit + Opus 4.8 chat editor), **one
locked ATS format** for everyone, **two entry points** (standalone Resume section + per-analysis)
sharing one `ResumeEditor` component, **versioning** (Default + create/switch/rename/delete),
per-user **always/never rules**, **master-as-base** tailoring (full profile stays the knowledge
base), scoped **Opus→Sonnet fallback** (chat-edit path, breaker-open only), and first-class
**truthfulness/hallucination control** (grounded prompts → deterministic faithfulness validator
→ user-visible warnings → no silent save-to-master).

Note: the prior deploy blocker (v1.4.0, missing SSM `/jobfit/staging/sentry-dsn`) is UNRELATED
to this branch and still open on the deploy side — see git history / previous handoff if resuming
that thread.

## Next Action

Await user review of the spec. If approved, invoke the **writing-plans** skill to produce the
step-by-step implementation plan following §13 build sequence. Do NOT start implementation
before the plan is approved.

## Why It Stopped

Awaiting user review of the written spec (brainstorming skill's user-review gate).

## In-Flight

- `docs/superpowers/specs/2026-07-22-resume-editor-design.md` (new spec — being committed)
- `HANDOFF.md` (this file)

## Open Questions

- Cover-letter chat editing: full parity now vs resume-first + follow-up (spec §14). Defers
  cleanly with no data-model change.
- Optional Layer-3 LLM faithfulness judge: keep off (`resume_faithfulness_judge_enabled=False`)
  until the deterministic Layer-2 validator shows gaps in real use.
- master-as-base couples into the `resume_tailorer` prompt + pipeline (spec §7) — confirmed in
  principle; verify no regression when implementing.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | Not run this session (docs-only change) |
| `make lint` | Not run this session (docs-only change) |
| `make check` | Not run this session (docs-only change) |
