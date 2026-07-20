# Session Handoff

**Updated:** 2026-07-20
**Branch:** main (synced with origin/main at `658fa00`)

---

## Current State

Shipped **v1.4.0** to `main`: the whole `feat/sentry-error-alerting` feature + the resume OCR
fallback, merged via `--no-ff` merge commit `658fa00`, pushed, tagged `v1.4.0`, tag pushed.
The tag triggered the **Deploy AWS ECS** workflow — which **FAILED at the pre-deploy migration
gate**. Production was NOT touched: no ECS service was rolled out, prod still runs **v1.3.1**.

- Resume OCR fix: fully verified this session (`docker build --target api` clean; `tesseract 5.5.0`
  / `pdftoppm 25.03.0` resolve in-image; `pytesseract`/`pdf2image`/`cv_parser` import + reach the
  binaries). That risk is closed.
- Lint/format re-checked clean before merge (`ruff check` + `ruff format --check`).

## Why It Stopped

User asked to stop the session. Deploy is **blocked awaiting a user decision** (see Next Action).

## Next Action — DEPLOY IS BLOCKED, needs user input

Deploy run `29759957641` failed with:
```
stopCode: TaskFailedToStart
ResourceInitializationError: unable to retrieve secrets from ssm:
invalid ssm parameters: /jobfit/staging/sentry-dsn
```
Root cause: commit `4574027` added a `SENTRY_DSN` secret ref
(`arn:aws:ssm:eu-west-2:896476315730:parameter/jobfit/staging/sentry-dsn`) to all three task-defs
(`infra/aws/task-definitions/{api,worker,beat}.json`), but that SSM parameter was **never created**.
Confirmed missing: `/jobfit/staging/` has 7 other params (anthropic-api-key, database-url,
jwt-secret, …) but no `sentry-dsn`. This is a missing provisioning step, NOT a code bug — the
infra README even lists it as required setup.

Two ways forward (user must pick):
1. **Provision the DSN** (recommended — the release IS the error alerting). Local AWS admin creds
   are available (`jobfit-cli-admin` @ account `896476315730`), so once the user supplies the DSN:
   ```
   aws ssm put-parameter --name /jobfit/staging/sentry-dsn --type SecureString \
     --value "<DSN>" --region eu-west-2
   gh run rerun 29759957641 --failed      # resumes deploy from the failed step
   ```
2. **Ship without Sentry**: remove the `SENTRY_DSN` secret block from the three task-defs, cut a
   new tag (v1.4.1), redeploy. Leaves error alerting inert until the DSN is added later.

## In-Flight

- **Uncommitted:** this `HANDOFF.md` update only (working tree otherwise clean, on `main`).
- Docker image `jobfit-api:ocr-check` still present locally from verification — can be pruned.
- Local branch `feat/sentry-error-alerting` still exists (also pushed to origin); now fully merged
  into main — safe to delete when convenient.

## Open Questions

- **SENTRY_DSN provisioning** (the blocker above). The DSN value was deliberately redacted from the
  repo (commit `06258f4`); it must come from the user — do not dig it out of git history or guess.
- Note the SSM path namespace is `/jobfit/staging/…` even though the deploy targets the prod
  `jobfit-cluster`. Appears intentional (single-account naming) since the 7 working secrets use the
  same prefix — worth a glance to confirm it's not a staging/prod mixup.
- OCR path still not exercised against a real scanned PDF end-to-end (nice-to-have; fast path
  unchanged so low risk).

## Verification Baseline

| Check | Result |
|---|---|
| `docker build --target api` | ✓ built clean (incl. resume-template compile guard) |
| `tesseract --version` / `pdftoppm -v` in image | ✓ 5.5.0 / 25.03.0 |
| `pytesseract.get_tesseract_version()` in image | ✓ 5.5.0 (wrapper reaches binary) |
| `ruff check` / `ruff format --check` (backend + tests) | ✓ clean |
| Deploy AWS ECS (tag v1.4.0, run 29759957641) | ✗ FAILED at migration gate — missing SSM `/jobfit/staging/sentry-dsn` |
| Production | Untouched — still on v1.3.1 (no service rolled out) |
