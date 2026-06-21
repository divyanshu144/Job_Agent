# Session Handoff

**Updated:** 2026-06-21
**Branch:** main — fully pushed (origin/main = HEAD = `eacd3d7`)

---

## Current State

The multi-tenant campaign feature and the FDE-readiness goal are complete (see
git history through `87117f2`). Since that baseline, work has been **deployment
and infrastructure** focused, all landed on `main`:

| Theme | Commits | What |
|---|---|---|
| Docker + local K8s | `dba75c7`, `7891775`, `369f0ab` | Multi-stage Dockerfile (api/worker/beat/frontend targets), docker-compose + prod override, k8s/ manifests, Docker Image CI, `make check` CI, `.dockerignore` |
| AWS ECS Fargate | `514a8aa`, `85505b8`, `120d3d3` | ECS deploy (`deploy-aws.yml`) + migration workflow (`aws-migrate.yml`), task definitions under `infra/aws/`, RDS Postgres + ElastiCache Redis, scale services before smoke test |
| Semantic memory | `6ebc598`, `93c9f55` | OpenAI embeddings (`text-embedding-3-small`) with pgvector storage + keyword fallback (`services/memory.py`, `MemoryChunk` model); retrieval typing fix |
| Migrations/CI | `9f5c4ce`, `9de7606`, `1fcf005`, `d56a92f` | startup migration head expectation, mypy decorator ignores, Ruff import order, frontend lockfile |
| Auth/UI | `f733461`, `4a10576` | cookie handling fix, UI changes |
| Resume PDF tooling | `eacd3d7` | TeX/`pdflatex` moved to a dedicated `backend-tex` Docker stage (api + worker only; beat has no TeX); smoke test asserts beat lacks pdflatex |

Documentation refreshed this session (CLAUDE.md, README.md, HANDOFF.md, todo.md)
to match the now much larger codebase — Postgres/pgvector/Redis/Celery,
multi-source discovery, resume PDF/DOCX rendering, semantic memory, and the
AWS/ECS deployment path. See **Open Questions** for the deferred review finding.

## Next Action

Nothing in flight. Candidate follow-ups (not committed to):
- **Dockerfile build-cache regression** (from /code-review of `eacd3d7`): the
  texlive install now sits below `COPY backend/` (in `backend-tex` FROM
  `backend-base`), so every backend source change re-downloads/installs texlive
  for the api+worker images. Move the apt/texlive layer above the source COPYs.
- Drop the redundant `chown -R appuser:appuser /app` in the `backend-tex` stage
  (no ownership change; bloats the image layer).
- `GET/PATCH /api/campaign/settings` route pair (enabled toggle + caps display)
- Per-run cost on `CampaignRunResponse`
- Redis storage_uri for the rate limiter when going multi-worker

## Why It Stopped

Documentation sync task complete; deployment work was already green and pushed.

## In-Flight

Working tree has pre-existing **uncommitted** edits to
`infra/aws/task-definitions/{api,beat,worker}.json` (CORS origin changed to
`https://app.jobfitapp.uk`) — made outside this session, left untouched. Decide
whether to commit these as part of the custom-domain cutover.

## Open Questions

- Confirm the custom domain (`app.jobfitapp.uk`) cutover plan before committing
  the task-definition CORS changes.

## Verification Baseline

Not re-run this session (docs-only changes). Last known green: `make check`
≈486 passed / ~82% (per `87117f2`). Run `make check` before the next code change.
