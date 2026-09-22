# Session Handoff

**Updated:** 2026-09-22
**Branch:** main (HEAD includes the merged `feat/railway-deploy` work)

---

## Current State

**Railway migration is live and fully verified.** `https://app.jobfitapp.uk` resolves via
Cloudflare CNAME → `cteyjilb.up.railway.app`, Railway issued a valid Let's Encrypt cert,
`/healthz` and `/api/health` both return 200 (`{"status":"ok","db":"ok","provider":"anthropic"}`)
— confirming nginx's `/api/` proxy, the api service, and its DB connection all work end-to-end
through the real domain.

All 6 services running: `pgvector` (Postgres + pgvector template, service literally named
`pgvector`), `Redis`, `api`, `worker`, `beat`, `frontend`. All 4 app services GitHub-connected
to `divyanshu144/Job_Agent`, tracking `main`, auto-deploy-on-push **enabled** (user's explicit
choice — considered and declined tag-gating as unneeded complexity for a single-maintainer
project). AWS is shut down; this is now the live deployment.

`feat/railway-deploy` was merged to `main` and pushed (fast-forward, no conflicts). AWS infra
code/docs are untouched and still in the repo for reference; `infra/aws/RUNBOOK.md` stays
gitignored per user decision.

### Bugs hit and fixed this migration (all documented in `tasks/lessons.md` + `docs/railway.md`)

1. `railway add --repo` tracks the GitHub default branch, not your current branch — caused an
   early confusing "wrong Docker stage built" red herring before `main` had the fix merged in.
2. `railway up` uploads the *linked project root*, not the shell's cwd — use
   `railway up <subdir> --path-as-root --service <name>` for a subdirectory service.
3. Dashboard-only fields with no CLI/config-as-code path: Custom Start Command, Root Directory,
   Docker build target. Confirmed against Railway's own docs + an open feedback-board request.
4. **Root Directory is not optional once GitHub auto-deploy is in play** — a one-off
   `--path-as-root` CLI deploy doesn't fix subsequent auto-deploys, which read the dashboard
   setting. Frontend broke a second time from this before the field was actually set.
5. Celery beat's default scheduler (`shelve`/`gdbm`) couldn't write `celerybeat-schedule` into
   the working directory on Railway's filesystem — crash-looped instantly, hit Railway's
   500 logs/sec rate limit. Fixed with `--schedule=/tmp/celerybeat-schedule`, applied in the
   Dockerfile CMD, `docker-compose.yml`, `infra/aws/task-definitions/beat.json`, **and** the
   Railway dashboard's Custom Start Command field (which shadows the Dockerfile CMD, so the
   code fix alone didn't take effect there until the dashboard field was updated to match).

### Final verification, per service

| Service | State |
|---|---|
| `api` | ✓ uvicorn running, alembic migrated to head, DB reachable, `/api/health` 200 through the real domain |
| `worker` | ✓ celery worker connected to Redis, tasks registered, `mingle: sync complete` |
| `beat` | ✓ scheduler running clean, no crash (post `/tmp` schedule-path fix) |
| `frontend` | ✓ nginx serving correct build, `/api/` proxy verified working through `app.jobfitapp.uk` |
| DNS/TLS | ✓ Cloudflare CNAME live (DNS-only), Let's Encrypt cert issued and verifying clean |

## Next Action

Only two items left, both user-owned:

1. **Product smoke test** through the real UI at `https://app.jobfitapp.uk`: register, upload
   a CV, run an analysis, download the PDF. Deliberately left to the user rather than done via
   curl with throwaway data — it's real profile data and a real billed LLM call. Offered to
   drive it via browser automation instead if the user would rather watch than do it — not
   taken up yet.
2. **Confirm nightly campaign spend caps** are set as wanted before trusting `worker`/`beat`
   with real traffic — they're already running, this is just a "make sure the caps are what
   you want" check, not a blocking technical step.

Nothing else is pending. If both of those come back clean, this migration is done — AWS can
stay shut down, `docs/railway.md` is the accurate runbook for any future redeploy-from-scratch.

## Why It Stopped

Natural pause after full infrastructure verification — waiting on the user for the two
items above, neither of which this session can/should do unilaterally.

## In-Flight

No uncommitted changes. `tasks/lessons.md` and `tasks/todo.md` updates for this session's
two bug fixes (beat schedule path, frontend Root Directory) are about to be committed
alongside this HANDOFF write.

## Open Questions

- None blocking. Optional cleanup: delete the now-fully-merged `feat/railway-deploy` branch
  (local + remote) — not yet asked.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` (local, prior session) | 713 passed · 82.89% coverage ✓ |
| `make lint` (local, prior session) | ✓ clean (part of `make check`) |
| `make check` (local, prior session) | ✓ clean |
| Railway deployment | ✓ all 6 services healthy, verified end-to-end through `https://app.jobfitapp.uk` |
| Product smoke test (register/CV/analysis/PDF) | ⏳ not yet done — deferred to user |
