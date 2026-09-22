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

`worker` and `beat` are also confirmed rebuilt correctly (texlive/backend-tex stage present,
compile guard passed) — both currently run the default `uvicorn` command (same image as `api`)
since their Start Command hasn't been overridden yet. Railway has no CLI flag or config-as-code
path for Start Command, Root Directory, or build `--target` (confirmed via Railway's own docs and
an open feedback-board request — no secret `--target` support despite one misleading secondhand
source claiming otherwise). These are genuine dashboard-only fields, not a gap in our tooling.

`frontend` hit a second, separate bug: `railway up` uploads the *linked project's root*, not the
shell's cwd, so `cd frontend && railway up` still built the repo-root (backend) Dockerfile —
deployed "successfully" but crash-looped (tried connecting to Postgres with no `DATABASE_URL`,
since it's not the api service). Fixed with `railway up frontend --path-as-root --service
frontend` from the repo root, which correctly scopes the upload to `frontend/`. **Now confirmed
healthy**: nginx running, built with `nginx.railway.conf.template` (confirmed via build log —
Railway auto-forwards service vars as Dockerfile `ARG`s, no build-arg-specific field needed).
Both gotchas are now documented in `docs/railway.md`'s new "CLI gotchas" section and
`tasks/lessons.md`.

Couldn't smoke-test the `/api/` proxy through the real domain yet — Railway won't issue a TLS
cert for `app.jobfitapp.uk` until DNS actually resolves there (chicken-and-egg with the pending
Cloudflare change), and Railway refuses to generate a fallback `*.up.railway.app` domain once a
custom domain is already attached to a service. The CNAME target itself
(`cteyjilb.up.railway.app`) 404s directly — Railway's edge only routes it once the custom domain
is verified. This step genuinely needs the Cloudflare DNS change first.

## Next Action

Waiting on the user for 3 things (all handed off, none blocking each other):

1. **Dashboard fields** (`railway open`), no CLI path exists for these:
   - `worker` → Settings → Deploy → Custom Start Command =
     `celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=2`
   - `beat` → Settings → Deploy → Custom Start Command =
     `celery -A backend.celery_app:celery_app beat --loglevel=info`
   - Redeploy both after saving (`railway redeploy --service worker`/`beat` works fine).
   - `frontend` → Settings → Source → Root Directory = `frontend` (so future GitHub-triggered
     deploys build the right Dockerfile — today's fix used `--path-as-root`, which doesn't
     persist to the dashboard's own source config).
2. **Branch decision**: point every service's Settings → Source → Branch at
   `feat/railway-deploy`, or merge this branch to `main` now that Railway-side deploys are
   verified working (code was already `make check`-green before this session). Not yet asked.
3. **Cloudflare CNAME**: `app.jobfitapp.uk` → `cteyjilb.up.railway.app` (reconfirm the value
   with `railway domain --service frontend --json` in case it rotated), DNS-only (grey cloud)
   first, then Full (strict) SSL once Railway issues the cert. No Cloudflare access in this
   session, so this is 100% on the user.

Once those land: full smoke test per `docs/railway.md` (register, upload CV, run an analysis,
download the PDF — never hand-edit the database), then enable real traffic on worker + beat
(confirm nightly campaign spend caps first).

## Why It Stopped

Needs user input on 3 things (dashboard fields, branch-vs-merge decision, Cloudflare DNS) — none
of which this session can do (no dashboard/browser access for the first, a decision only the user
can make for the second, no Cloudflare access for the third).

## In-Flight

No uncommitted changes — `tasks/lessons.md`, `HANDOFF.md`, and `docs/railway.md` all committed
this session. All 4 GitHub-connected services (api/worker/beat/frontend) have a working deploy
live on Railway right now via `railway up`; nothing further needs pushing from this session until
the user's 3 items above are done.

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
| `worker` / `beat` on Railway | ✓ correct image (texlive present) — ⏳ still running default `uvicorn`, needs dashboard Start Command |
| `frontend` on Railway | ✓ confirmed — nginx running, correct config, `/api/` proxy path untestable until DNS cutover |
