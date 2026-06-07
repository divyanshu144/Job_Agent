# Session Handoff

**Updated:** 2026-06-07
**Branch:** feat/resume-latex (off `feat/campaign-orchestrator`) — committed, not merged/pushed

---

## Current State

**Prompt 3 COMPLETE — LaTeX resume tailoring → PDF, wired into the campaign orchestrator.**
TDD (4 tests written failing first). `make check` green (**263 passed, 77.69% cov**); ruff + mypy +
schema-drift pass. Pipeline target: cold email + tailored resume PDF attachment, **no cover letter**.

**What landed:**
- **Step 1 check:** `ResumeTailorerAgent` IS used by the main interactive pipeline (`orchestrator.py`
  Phase 2) — so it was **not** repurposed. The LaTeX flow is a **separate module**.
- **`backend/services/resume_latex.py`** — `tailor_resume_pdf(job_description, latex_source) -> bytes`:
  LLM (`_tailor_latex`, Sonnet) edits ONLY summary/skills/experience and preserves preamble/structure;
  writes `.tex` in a `TemporaryDirectory`; runs `pdflatex -interaction=nonstopmode -halt-on-error
  -output-directory {tmp} {tex}`; on non-zero exit retries ONCE with a self-correction prompt carrying
  the pdflatex log tail; on second failure raises `ResumeCompileError`. PDF bytes read before tempdir
  cleanup. Comment notes real runs need texlive (`pdflatex` on PATH).
- **`assets/resume.tex`** — minimal valid placeholder (`\documentclass{article}` + Summary/Skills/
  Experience) so the path is exercisable.
- **Orchestrator (`campaign_orchestrator.py`)**: renamed `_cover_letter` → `_cold_email` (still a
  no-op; Prompt 4). `_resume_tailor(job_id, job_description)` is now **real** — calls
  `tailor_resume_pdf(load_resume_latex())`, **PDF held in memory per-job, not persisted**. Loop
  captures `job.raw_text` before the session closes and passes it. `_record_failure` is now an
  **upsert** (so a job that fails *after* being queued is flipped to failed, not duplicated).

**Testing:** pdflatex is **mocked** (`subprocess.run`) — tests assert command shape, retry-on-failure
feeds the log tail to the correction prompt, and double-failure raises. CI needs no texlive. Campaign
logic tests mock `_resume_tailor`; a wiring test asserts it receives the job description.

## Next Action

Merge the campaign chain (`feat/campaign-orchestrator` → `feat/resume-latex`) to `main` + push on your
go, then **Prompt 4** (implement `_cold_email`, consuming the in-memory resume PDF as the attachment).

## In-Flight

Committed on `feat/resume-latex`: `backend/services/resume_latex.py`,
`backend/services/campaign_orchestrator.py`, `assets/resume.tex`,
`tests/test_services/test_resume_latex.py`, `tests/test_services/test_campaign_orchestrator.py`,
this HANDOFF. Branch stacks on `feat/campaign-orchestrator` (Prompt 2), which is not yet on `main`.

## Open Questions

1. Merge order: `feat/campaign-orchestrator` then `feat/resume-latex` → `main` (stacked). Do it now?
2. Prompt 4 contract: `_cold_email` consumes the resume PDF — thread the bytes from `_resume_tailor`
   into `_cold_email(job_id, resume_pdf)` (capture in the loop), and presumably `_contact_find` runs
   first to supply the recipient. Confirm step order/signatures when we get there.
3. `feat/job-board-scrapers` + `feat/referral-clean` still linger from the cleanup pass.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 263 passed, 1 deselected, 77.69% coverage |
| new tests | ✓ 3 resume_latex (cmd shape / retry-feeds-log / double-fail-raises) + 1 orchestrator wiring |
| texlive | not required in CI (pdflatex mocked); real runs need it on PATH |
