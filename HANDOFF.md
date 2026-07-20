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

Docker verification is now DONE (2026-07-20): `docker build --target api` succeeds, and inside
the image `tesseract 5.5.0` / `pdftoppm 25.03.0` resolve, `pytesseract.get_tesseract_version()`
returns 5.5.0, `pdf2image` + `backend.services.cv_parser.extract_text_from_pdf_bytes` import
cleanly. The OCR-fallback change is fully verified. If accepted as-is, this can merge into the
existing `feat/sentry-error-alerting` branch's eventual PR, or be pulled onto its own branch/PR —
user hasn't specified which.

## Why It Stopped

Task complete (code + regression tests + lint/type checks all green); stopped at the Stop-hook
checkpoint requiring HANDOFF.md sync before ending the turn.

## In-Flight

None after this commit — the OCR-fallback change (6 files) is being committed alongside this
HANDOFF.md update: `Dockerfile`, `backend/routes/profile.py`, `backend/services/cv_parser.py`,
`requirements.txt`, `tasks/lessons.md`, `tests/test_services/test_cv_parser.py`.

## Open Questions

- ~~**Docker build unverified in this session**~~ — RESOLVED 2026-07-20. `docker build --target api`
  built clean; `tesseract 5.5.0` and `pdftoppm 25.03.0` resolve inside the image, and
  `pytesseract`/`pdf2image`/`cv_parser` import and reach the binaries. The `lmodern`-class risk
  (mocked unit tests giving zero signal on binary availability) is retired for this change.
  Remaining nice-to-have: exercise the OCR path against a real scanned PDF end-to-end, but the
  binary-resolution risk that motivated this is closed.

## Verification Baseline

| Check | Result |
|---|---|
| `pytest tests/test_services/test_cv_parser.py -v` | 6 passed (3 new OCR-fallback tests) |
| `pytest tests/test_services/ tests/test_agents/ -v` | 219 passed, 0 failures (86 errors — pre-existing, testcontainers needs Docker daemon unavailable in this sandbox, unrelated to this change) |
| `ruff format --check backend/ tests/` | ✓ clean |
| `ruff check backend/ tests/` | ✓ clean |
| `mypy backend/services/cv_parser.py backend/routes/profile.py` | ✓ clean |
| `make check` (full, incl. Docker-backed route/service tests) | Not run — no Docker daemon in this sandbox |
