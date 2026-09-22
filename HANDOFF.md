# Session Handoff

**Updated:** 2026-09-22
**Branch:** feat/railway-deploy (off docs/railway-plan, off main `f2845a3`; HEAD `f317303`)

---

## Current State

Railway project **`jobfit-agent`** is created and live-in-progress (no longer just planned).
Domain confirmed with user: `app.jobfitapp.uk` (same zone as the old AWS deploy, reusing the
`app` subdomain so only the Cloudflare CNAME target changes).

All 6 services provisioned: `pgvector` (Postgres w/ pgvector, Railway template `3jJFCA`,
image `pgvector/pgvector:pg18`), `Redis`, `api`, `worker`, `beat`, `frontend` — the latter four
GitHub-connected to `divyanshu144/Job_Agent`. Env vars set on api/worker/beat (secrets sourced
from local `.env`: ANTHROPIC/OPENAI/HUNTER/REED/ADZUNA/GMAIL keys; fresh `JWT_SECRET` generated,
not reused from AWS; `DATABASE_URL`/`REDIS_URL` via `${{pgvector.*}}` / `${{Redis.REDIS_URL}}`
reference vars — note service is named `pgvector`, not `Postgres`, so runbook's `${{Postgres.*}}`
examples don't literally apply). `NGINX_CONF=nginx.railway.conf.template` set on frontend (Railway
auto-forwards service vars as Dockerfile `ARG`s — confirmed via docs, matches our existing
`ARG NGINX_CONF` line, no build-arg-specific field needed). Custom domain `app.jobfitapp.uk`
attached to `frontend`; Cloudflare CNAME **not yet repointed** (still shows the old AWS ALB target).

**Bug found and fixed (see `tasks/lessons.md` 2026-09-22 entry):** `railway add --repo` links the
GitHub repo's *default branch* (`main`), not the current branch. `main`'s Dockerfile still has
`beat` as the textually-last stage (pre-dates this branch's reorder to put `api` last), so every
service's first auto-deploy built and ran `beat` regardless of service name — confirmed via build
logs (none reached `backend-tex`/texlive) and runtime logs (`beat: Starting...` on all three).
Fixed by deploying via `railway up` (uploads local working directory, branch-agnostic) instead of
waiting on the GitHub-triggered build.

`api` is **confirmed fixed and healthy**: rebuilt via `railway up`, texlive/backend-tex stage
present, resume-template compile guard passed at build time, uvicorn running, alembic migrated
cleanly through `0014_resume_documents` (head), confirming the `DATABASE_URL` reference var to
the `pgvector` service works.

`worker`, `beat`, `frontend` redeploys via `railway up` were **in progress (backgrounded) when
this session paused** — outcome unknown, must be checked first thing next session (see Next Action).
Even once those finish, `worker`/`beat` will still be running the **default `uvicorn` command**
(same image as `api`) until their Start Command is overridden — Railway has no CLI flag or
config-as-code path for this when services share a root directory, confirmed via Railway docs
and a community feedback thread (no `--target` support either, despite one misleading secondhand
PR summary claiming otherwise — verified against Railway's own feedback board that it's still an
open feature request). This is a genuine dashboard-only step, not a gap in our tooling.

## Next Action

1. Check the 3 backgrounded `railway up` builds (worker, beat, frontend) — re-run and inspect,
   don't assume success:
   `railway logs --service <name> --build -n 60 --latest` (look for `backend-tex`/texlive lines)
   and `railway logs --service <name> --deployment -n 20 --latest` (look for the actual running
   process, not just "Starting Container").
2. In the Railway dashboard (`railway open`), set on **worker**: Settings → Deploy → Custom Start
   Command = `celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=2`.
   On **beat**: same field = `celery -A backend.celery_app:celery_app beat --loglevel=info`.
   Redeploy both after saving (dashboard "Redeploy" or `railway redeploy --service worker`/`beat`).
3. On **frontend**, dashboard Settings → Source → Root Directory = `frontend` (needed so future
   GitHub-triggered deploys build the right Dockerfile — today's `railway up` deploy bypassed this
   by running from inside `frontend/` directly, but that fix doesn't persist to the dashboard).
4. Decide + fix the GitHub branch mismatch for future auto-deploys: either set each service's
   Settings → Source → Branch to `feat/railway-deploy`, or merge this branch to `main` (code is
   verified/tested — `make check` was green before this session; Railway-side verification is what
   this session's work was for). User has not been asked which yet.
5. User must repoint the Cloudflare CNAME: `app.jobfitapp.uk` → `cteyjilb.up.railway.app`
   (get the current required value fresh via `railway domain --service frontend --json` in case
   it rotated), DNS-only (grey cloud) first, then Full (strict) SSL once Railway issues the cert.
6. Full smoke test per `docs/railway.md`: register, upload CV, run an analysis, download the PDF.
   Never hand-edit the database.
7. Only then enable real traffic on worker + beat (confirm nightly campaign spend caps first).

## Why It Stopped

Stop-hook checkpoint (uncommitted `tasks/lessons.md`, 30-min rule) while 3 backgrounds deploys
were still running — not a natural stopping point, mid-deploy. No blocking user question pending;
purely a "background work in flight" pause.

## In-Flight

- `tasks/lessons.md` — modified, being committed alongside this HANDOFF update.
- 3 background `railway up` processes (worker, beat, frontend) — may have finished by next read;
  check with the commands in Next Action step 1 rather than trusting exit status alone (a
  "SUCCESS" deploy status does NOT mean the correct stage/process is running — that's exactly
  today's bug).

## Open Questions

- Cloudflare DNS change: user needs to make it themselves (no Cloudflare API access in this
  session) — CNAME `app.jobfitapp.uk` → `cteyjilb.up.railway.app` (reconfirm value first).
- GitHub branch for future auto-deploys: point services at `feat/railway-deploy`, or merge to
  `main` now? Not yet asked.
- Whether `infra/aws/RUNBOOK.md` stays gitignored — user already answered: **yes, stays gitignored.**
- Untested: whether Railway's private DNS resolver `[fd12::10]` actually works for the frontend's
  nginx `/api/` proxy once real traffic flows (was only verified against a stub API in Docker
  locally, per the prior session).

## Verification Baseline

| Check | Result |
|---|---|
| `make test` (local, prior session) | 713 passed · 82.89% coverage ✓ |
| `make lint` (local, prior session) | ✓ clean (part of `make check`) |
| `make check` (local, prior session) | ✓ clean |
| `api` on Railway | ✓ confirmed — uvicorn running, migrated to head, DB reachable |
| `worker` / `beat` / `frontend` on Railway | ⏳ unknown — check before trusting |
