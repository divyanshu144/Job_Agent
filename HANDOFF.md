# Session Handoff

**Updated:** 2026-09-22
**Branch:** main (merged `feat/railway-deploy`, HEAD `2fa58f8`)

---

## Current State

Railway project **`jobfit-agent`** is live. Domain confirmed with user: `app.jobfitapp.uk`
(same zone as the old AWS deploy, reusing the `app` subdomain so only the Cloudflare CNAME
target changes). `feat/railway-deploy` was merged (fast-forward, clean linear history) and
pushed to `main` — Railway's services already tracked `main` by default (that's what caused
the original bug below), so this is also what they'll auto-deploy from going forward. User
explicitly chose to **keep Railway's default deploy-on-push-to-main** rather than add
tag-gating — a `deploy-railway.yml` tag-triggered workflow (mirroring `deploy-aws.yml`) was
written, then deliberately reverted (commit `2fa58f8`) as unnecessary complexity. No
`RAILWAY_TOKEN` secret needed.

All 6 services provisioned: `pgvector` (Postgres w/ pgvector, Railway template `3jJFCA`,
image `pgvector/pgvector:pg18`), `Redis`, `api`, `worker`, `beat`, `frontend` — the latter four
GitHub-connected to `divyanshu144/Job_Agent`, tracking `main`. Env vars set on api/worker/beat
(secrets sourced from local `.env`: ANTHROPIC/OPENAI/HUNTER/REED/ADZUNA/GMAIL keys; fresh
`JWT_SECRET` generated, not reused from AWS; `DATABASE_URL`/`REDIS_URL` via `${{pgvector.*}}` /
`${{Redis.REDIS_URL}}` reference vars — note service is named `pgvector`, not `Postgres`, so
runbook's `${{Postgres.*}}` examples don't literally apply). `NGINX_CONF=nginx.railway.conf.template`
set on frontend (Railway auto-forwards service vars as Dockerfile `ARG`s). Custom domain
`app.jobfitapp.uk` attached to `frontend`; Cloudflare CNAME **not yet repointed** (still shows
the old AWS ALB target).

**Two bugs found and fixed this session** (full detail in `tasks/lessons.md` and
`docs/railway.md`'s "CLI gotchas" section):
1. `railway add --repo` links the GitHub repo's default branch (`main`), not the branch you're
   on locally — and at the time, `main`'s Dockerfile still had `beat` as the last stage, so
   every service's first auto-deploy built and ran `beat` regardless of service name. Now moot
   since `main` has the fix (merged above), but the underlying CLI behavior is still true.
2. `railway up` uploads the *linked project's root*, not the shell's cwd — `cd frontend &&
   railway up` still built the repo-root Dockerfile and crash-looped. Fixed with
   `railway up frontend --path-as-root --service frontend`.

**Confirmed healthy right now:** `api` (uvicorn running, alembic migrated to head
`0014_resume_documents`, DB reachable) and `frontend` (nginx running, correct
`nginx.railway.conf.template` config). **`worker` and `beat`** have the correct image
(texlive present, compile guard passed) but are still running the default `uvicorn` command —
their Start Command has not been set yet (dashboard-only field, no CLI/config-as-code path;
confirmed against Railway's own docs and an open feedback-board request).

Couldn't smoke-test the `/api/` proxy through the real domain yet — Railway won't issue a TLS
cert for `app.jobfitapp.uk` until DNS actually resolves there, and it refuses to generate a
fallback `*.up.railway.app` domain once a custom domain is attached. This needs the Cloudflare
DNS change first.

## Next Action

User was mid-walkthrough of the Railway dashboard fields when they redirected the branch/tag
plan (see above) — the dashboard steps below are unaffected by that change and still pending:

1. In the Railway dashboard (`railway open`):
   - `worker` → Settings → Deploy → Custom Start Command =
     `celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=2`
   - `beat` → Settings → Deploy → Custom Start Command =
     `celery -A backend.celery_app:celery_app beat --loglevel=info`
   - Redeploy both after saving (`railway redeploy --service worker`/`beat` works too).
   - **Do NOT disable autodeploy** on any service (that was part of the reverted tag-gating
     plan) — leave it on, per user's decision to keep default deploy-on-push-to-main.
2. User must repoint the Cloudflare CNAME: `app.jobfitapp.uk` → `cteyjilb.up.railway.app`
   (reconfirm the value with `railway domain --service frontend --json` in case it rotated),
   DNS-only (grey cloud) first, then Full (strict) SSL once Railway issues the cert. No
   Cloudflare access in this session — 100% on the user.
3. Once worker/beat + DNS land: full smoke test per `docs/railway.md` (register, upload CV,
   run an analysis, download the PDF — never hand-edit the database).
4. Only then enable real traffic on worker + beat (confirm nightly campaign spend caps first).

## Why It Stopped

Mid-conversation, waiting on the user to actually click through the dashboard fields in step 1
above (this session can't set Start Command via CLI) and to make the Cloudflare DNS change (no
Cloudflare access in this session).

## In-Flight

No uncommitted changes. `main` now has all the Railway work (merged from `feat/railway-deploy`);
the `feat/railway-deploy` branch still exists locally/remotely but is fully merged — safe to
delete once the user confirms, not yet asked.

## Open Questions

- Cloudflare DNS change: user needs to make it themselves — CNAME `app.jobfitapp.uk` →
  `cteyjilb.up.railway.app` (reconfirm value first).
- Whether `infra/aws/RUNBOOK.md` stays gitignored — user already answered: **yes, stays gitignored.**
- Untested: whether Railway's private DNS resolver `[fd12::10]` actually works for the frontend's
  nginx `/api/` proxy once real traffic flows (was only verified against a stub API in Docker
  locally, per the prior session).
- Delete the now-fully-merged `feat/railway-deploy` branch? Not yet asked.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` (local, prior session) | 713 passed · 82.89% coverage ✓ |
| `make lint` (local, prior session) | ✓ clean (part of `make check`) |
| `make check` (local, prior session) | ✓ clean |
| `api` on Railway | ✓ confirmed — uvicorn running, migrated to head, DB reachable |
| `worker` / `beat` on Railway | ✓ correct image (texlive present) — ⏳ still running default `uvicorn`, needs dashboard Start Command |
| `frontend` on Railway | ✓ confirmed — nginx running, correct config, `/api/` proxy path untestable until DNS cutover |
