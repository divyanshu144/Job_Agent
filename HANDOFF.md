# Session Handoff

**Updated:** 2026-06-22
**Branch:** `main` — clean, pushed (`4b79da1`). Nothing in flight.

---

## Recently shipped (this session, all on main)

- **Resume→YAML auto-populate** (`1d49904`) — merged, runtime-verified by running the app.
- **Dockerfile texlive layer-order fix** (`dad30a3`) — texlive installs on a source-independent
  `python-deps` layer; api/worker copy the app from `backend-base` via `COPY --from`. Backend
  code changes no longer reinstall texlive (proven: rebuild after editing `backend/main.py`
  showed the texlive layer `CACHED`). Dropped the redundant `chown -R /app`. `beat` still TeX-free.
- **CORS cutover to `https://app.jobfitapp.uk`** (`fb63edc`) — domain fully wired (DNS→ALB,
  ACM cert ISSUED, HTTPS:443 listener, frontend + API served at the domain). ECS deploy
  **succeeded**; API now on `jobfit-api:27` with `CORS_ORIGINS=https://app.jobfitapp.uk`.
  All services healthy (running=desired=1, COMPLETED).
- **Tag-based deploys** (`4b79da1`) — `deploy-aws.yml` no longer deploys on push to `main`;
  it triggers only on `v*` tags or manual `workflow_dispatch`. (Previously every push,
  including docs, auto-deployed to prod.)

### Deploy process now
Release = explicit tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. Migrations are manual
(`aws-migrate.yml`, workflow_dispatch). The local docker stack was rebuilt onto the merged code.

### Notes / follow-ups
- The worker service occasionally fails to stabilize within the deploy wait window (ECS
  deployment circuit breaker rolls back to last-good → no outage, but the run shows failure).
  Saw it once this session; the CORS deploy stabilized fine. Watch for recurrence.
- Deferred: wire discovery `search_profiles` to per-user `yaml_data`; remove dormant non-`links`
  `ProfileReviewData` fields.

---

## Done — auto-populate YAML profile from resume (MERGED to main, verified via running app)

**Problem fixed:** the `match_scorer`/`job_parser` only see `build_compact_profile`
= `yaml_data` + first 500 chars of CV; uploading a resume left `yaml_data` empty, so the
score was computed against almost nothing. Now the resume auto-populates `yaml_data`.

**Shipped on branch `feat/resume-yaml-autopopulate`** (spec: `docs/superpowers/specs/2026-06-21-resume-to-yaml-autopopulate-design.md`, plan: `docs/superpowers/plans/2026-06-21-resume-to-yaml-autopopulate.md`):
- `ExtractedProfile` schema + `extracted_profile_to_yaml()` serializer (`537308f`)
- `ProfileExtractorAgent` (Haiku) + `profile_extractor.md` prompt (`9ce244a`)
- `POST /profile/cv` auto-populates `yaml_data` every upload, fail-open preserves prior YAML (`9ca88a8`); test-isolation autouse stub (`afc9ab1`)
- `PUT /profile/yaml` editable YAML for all users, 422 on invalid YAML (`b33fa45`)
- Frontend: editable YAML for all users; structured form trimmed to Links only (`ab5c2cb`)

Each task passed a two-stage subagent review (spec compliance + code quality).

**Verification baseline:** `make check` → 561 passed, 1 deselected, 83.18% coverage, ruff/mypy/schema-drift clean. `cd frontend && npm run build` → clean (tsc + vite).

**Status:** merged to `main` (`1d49904`, fast-forward), pushed. Final whole-feature review = READY TO MERGE. Runtime-verified by running the app: upload → live extractor populated `yaml_data`; `PUT /profile/yaml` persisted; 422 on bad YAML; 401 unauth; 400 empty file. The running docker `api`/`worker`/`beat` were rebuilt onto the merged code.

**Follow-ups (out of scope, deferred):** wire discovery `search_profiles` to per-user `yaml_data` (today reads on-disk `data/candidate_profile.yaml`, `discovery.py:57`); remove the now-dormant non-`links` `ProfileReviewData` fields. Also still pending: the stashed `infra/aws/task-definitions/*` CORS cutover decision (`stash@{0}`).

---

## Current State (prior, shipped)

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
