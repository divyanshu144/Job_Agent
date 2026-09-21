# Session Handoff

**Updated:** 2026-09-21
**Branch:** docs/railway-plan (off main at `f2845a3`)

---

## Current State

Planning a Railway deployment. AWS is shut down to stop cost; the goal is just to get the app running again cheaply. **No application code changed.** This session only read the deploy surface (`Dockerfile`, `docker-compose.prod.yml`, `frontend/nginx.prod.conf`, `backend/config.py`) and wrote the plan into `tasks/todo.md` under "Railway deployment". The eval-fixture decision from the previous handoff is resolved (merged in `f2845a3`, single source of truth for the cover-letter floor).

Findings that shape the plan: `nginx.prod.conf` has no `/api` proxy (AWS ALB did the routing), so the Railway frontend needs one to keep cookie-JWT auth same-origin; Railway likely cannot select a Docker `--target`, so api/worker/beat need per-service Dockerfiles; `run_migrations_on_startup` already defaults to true, so migrations should run on the api service only.

## Next Action

Get the user's answers to the two open questions below, then start step 1 of the plan in `tasks/todo.md`: add `Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.beat` (reusing the existing stages) and an env-driven `/api/` proxy (with `proxy_buffering off` for the SSE route) in `frontend/nginx.prod.conf`; build the images locally to verify. Railway CLI login (`railway login`) is needed only for the later project-setup step.

## Why It Stopped

Awaiting user answers on data and domain before implementing (per the "check in before implementation" rule).

## In-Flight

- `tasks/todo.md` (plan section added)
- `HANDOFF.md`

## Open Questions

- Fresh database, or restore the old RDS snapshot (users, saved jobs, analyses)? Fresh is much simpler.
- Free `*.up.railway.app` URL for now, or a custom domain?
- Whether `infra/aws/RUNBOOK.md` stays gitignored (carried over; repo is public).

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | not run this session (docs-only change) |
| `make lint` | not run this session (docs-only change) |
| `make check` | not run this session (docs-only change) |
