# Session Handoff

**Updated:** 2026-06-22
**Branch:** `main` — clean, pushed (`e861af9`). Tag **`v1.0.0`** cut & deployed. Nothing in flight.

---

## State at session end

**`v1.0.0` is released and live in production at `https://app.jobfitapp.uk`.** Production
smoke-tested (non-destructive): frontend HTTPS 200, valid ACM cert, `GET /api/profile` → 401,
released `PUT /api/profile/yaml` → 401 (feature live), CORS allows the domain & blocks others.
The v1.0.0 deploy rolled the API to `jobfit-api:28` (COMPLETED, healthy); the run was still
finishing the remaining services when the session ended — it self-heals via the circuit breaker.

### Shipped this session (all on `main`)
- **Resume→YAML auto-populate** (`1d49904`) — LLM `ProfileExtractorAgent` fills `yaml_data` on
  CV upload (fail-open); `PUT /profile/yaml` editable YAML for all users; form trimmed to Links.
  Runtime-verified locally. (Detail section below.)
- **Dockerfile texlive layer-order fix** (`dad30a3`) — texlive on a source-independent
  `python-deps` layer; backend edits no longer reinstall it (proven CACHED). `beat` still TeX-free.
- **CORS cutover** (`fb63edc`) — API `CORS_ORIGINS=https://app.jobfitapp.uk`; domain fully wired.
- **Deploy hardening:** tag-based trigger (`4b79da1`), concurrency guard (`46c88de`), ECS
  **deployment circuit breaker + rollback on all 4 services**, and **beat pinned to a singleton**
  (`min 0 / max 100`, AZ rebalancing disabled — never two schedulers). These service-level
  settings are documented in `infra/aws/README.md` (`e861af9`) — they live on AWS, NOT in the
  repo, so re-apply them (commands in that README) if a service is recreated.

### Deploy process now
Release = `git tag vX.Y.Z && git push origin vX.Y.Z` (only `v*` tags or manual dispatch deploy).
Migrations are manual (`aws-migrate.yml`).

### Next action (cold-start)
Nothing required. Optional: confirm the `v1.0.0` deploy run finished green
(`gh run list --workflow=deploy-aws.yml`); if it didn't, the circuit breaker rolled back to
last-good (no outage) — investigate that run's logs.

### Open items / deferred
- The **`infra/aws/task-definitions/*` files committed the new CORS** already (no stash left).
- Deferred follow-ups: wire discovery `search_profiles` to per-user `yaml_data` (today reads
  on-disk `data/candidate_profile.yaml`); remove the dormant non-`links` `ProfileReviewData` fields.
- Resolved myth: the earlier "worker failed to stabilize" was **overlapping concurrent deploys**
  (push-storm superseding each other's deployment), not a worker fault — fixed by tag-based +
  concurrency guard. See `tasks/lessons.md` 2026-06-22.

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
