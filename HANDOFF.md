# Session Handoff

**Updated:** 2026-07-25
**Branch:** feat/resume-editor-chat

---

## Current State

Resume Editor Plans 1-5 are merged. This session fixed a download bug: the resume PDF
renderer (`resume_latex_template.py`) silently truncated user-curated content (summary→52
words, experience[:3]/3 bullets/24 words, projects[:3], skills[:24], education[:2]) and
ignored `content.headline`, so PDF downloads didn't match the editor/preview/DOCX
("missing parts" + "changes not saved"). Added a `faithful=True` WYSIWYG mode threaded
through the renderer that disables every cap and allows multi-page output; the download
route (`history.py`) now uses it, and the edited headline renders as a tagline in the PDF
header. Fix verified against a real "Tailored" fork (101-word summary now renders verbatim,
all 18 skills, clean 2-page PDF) and baked into the rebuilt Docker api image (:8080, healthy).

## Next Action

Commit the working tree (4 modified files listed under In-Flight), then have the user
re-download from the editor on localhost:8080 to visually confirm PDF = preview = DOCX.
Deferred follow-ups if resumed: Plan 6 (cover-letter mode); wire version-card "N roles"
to pull from resume content instead of the review record.

## Why It Stopped

Task complete — bug fixed, `make check` green, Docker image rebuilt. Committing per Stop hook.

## In-Flight

Uncommitted (about to commit):
- backend/services/resume_latex_template.py — faithful render mode + headline tagline
- backend/routes/history.py — PDF download passes `faithful=True`
- tests/test_services/test_resume_latex_template.py — faithful-vs-capped regression tests
- tasks/lessons.md — 2026-07-25 lesson entry

## Open Questions

Faithful downloads can now be 2 pages instead of force-fit to one. This is the intended
WYSIWYG trade-off for hand-curated resumes (one-page discipline kept only for the
auto-generated pipeline output). No action needed unless the user wants a one-page cap back.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | 713 passing · 82.88% coverage ✓ |
| `make lint` | ✓ clean (ruff + mypy on changed files) |
| `make check` | ✓ clean (fmt + lint + test) |
