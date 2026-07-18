# Session Handoff

**Updated:** 2026-07-18
**Branch:** feat/sentry-error-alerting

---

## Current State

Fixed the resume-upload bug where scanned/image-only PDFs threw "Could not extract enough
resume text from the uploaded file" (pypdf extracts 0 chars from a PDF with no text layer).
Added an OCR fallback (Option A): `extract_text_from_pdf_bytes` in `backend/services/cv_parser.py`
now retries via `pdf2image.convert_from_bytes` + `pytesseract.image_to_string` whenever the pypdf
fast path yields under 20 chars; the pypdf path is unchanged/still tried first. `requirements.txt`
gained `pytesseract` + `pdf2image`; `Dockerfile`'s `backend-tex` stage (api image only, same
reasoning as the existing `lmodern` line) gained the `poppler-utils` + `tesseract-ocr` system
packages those libraries wrap. `backend/routes/profile.py`'s 400 error message now says "even
after attempting OCR" when the failed extraction was a PDF. Task done via `debug-playbook` skill.

## Next Action

Nothing in flight after this commit. Before this is considered fully verified: build the `api`
Docker target and confirm `tesseract --version` / `pdftoppm -v` resolve inside the image (no
Docker daemon was available in this session — see Open Questions). If accepted as-is, this can
merge into the existing `feat/sentry-error-alerting` branch's eventual PR, or be pulled onto its
own branch/PR — user hasn't specified which.

## Why It Stopped

Task complete (code + regression tests + lint/type checks all green); stopped at the Stop-hook
checkpoint requiring HANDOFF.md sync before ending the turn.

## In-Flight

None after this commit — the OCR-fallback change (6 files) is being committed alongside this
HANDOFF.md update: `Dockerfile`, `backend/routes/profile.py`, `backend/services/cv_parser.py`,
`requirements.txt`, `tasks/lessons.md`, `tests/test_services/test_cv_parser.py`.

## Open Questions

- **Docker build unverified in this session** (no daemon available): the `poppler-utils` /
  `tesseract-ocr` apt-get addition to the `backend-tex` Dockerfile stage has not been build- or
  runtime-tested. Unit tests mock the OCR calls, so they give zero signal on whether the binaries
  actually resolve in the built image — this is the same risk class as the `lmodern` incident
  logged in `tasks/lessons.md` (2026-07-05). Logged as a fresh entry (2026-07-18) in the same
  file. Next session with Docker: `docker build --target api` then exercise the OCR path against
  a real scanned PDF before calling this closed.

## Verification Baseline

| Check | Result |
|---|---|
| `pytest tests/test_services/test_cv_parser.py -v` | 6 passed (3 new OCR-fallback tests) |
| `pytest tests/test_services/ tests/test_agents/ -v` | 219 passed, 0 failures (86 errors — pre-existing, testcontainers needs Docker daemon unavailable in this sandbox, unrelated to this change) |
| `ruff format --check backend/ tests/` | ✓ clean |
| `ruff check backend/ tests/` | ✓ clean |
| `mypy backend/services/cv_parser.py backend/routes/profile.py` | ✓ clean |
| `make check` (full, incl. Docker-backed route/service tests) | Not run — no Docker daemon in this sandbox |
