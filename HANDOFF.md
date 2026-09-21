# Session Handoff

**Updated:** 2026-09-21
**Branch:** feat/railway-deploy (off docs/railway-plan, off main `f2845a3`)

---

## Current State

Railway deployment: **code changes are done and verified; nothing is deployed yet.** AWS is shut down for cost. Decisions made: fresh database (no RDS restore), custom domain already bought on Cloudflare.

Changes: `Dockerfile` now ends with the `api` stage (Railway cannot pick `--target`; worker/beat reuse the image with a start-command override, replacing the earlier per-service-Dockerfile idea). `frontend/nginx.railway.conf.template` proxies `/api/` to `api.railway.internal:8000` so cookie-JWT auth stays same-origin; `frontend/Dockerfile` now installs the config as an nginx template (envsubst) with `PORT`/`API_UPSTREAM`/`DNS_RESOLVER` defaults. Runbook is `docs/railway.md` (variable names only; repo is public).

Verified: proxy path/proto/SPA fallback/healthz against a stub API in Docker; existing `nginx.conf` and `nginx.prod.conf` render byte-identical; default backend build yields the uvicorn image with pdflatex; `make check` green (713 passed, 82.9% coverage).

## Next Action

Follow `docs/railway.md` "First deploy checklist": run `railway login` (`! railway login` in the prompt), create the project (Postgres pgvector template, Redis, `api`, `frontend`), set variables, attach the custom domain (needs the domain name for `CORS_ORIGINS`), add the Cloudflare CNAME as DNS-only first, then smoke test through the app. Enable `worker` and `beat` last.

## Why It Stopped

Needs user input: the domain name, and Railway CLI login for the setup steps.

## In-Flight

No uncommitted changes (all committed on `feat/railway-deploy`).

## Open Questions

- What is the domain name (for `CORS_ORIGINS` and the CNAME)?
- Whether `infra/aws/RUNBOOK.md` stays gitignored (carried over; repo is public).
- Untested assumptions to confirm on first deploy: Railway private DNS resolver `[fd12::10]` works with the nginx config; the `${{...}}` reference-variable syntax in `docs/railway.md`.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | 713 passed · 82.89% coverage ✓ |
| `make lint` | ✓ clean (part of `make check`) |
| `make check` | ✓ clean |
