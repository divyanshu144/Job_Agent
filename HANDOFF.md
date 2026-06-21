# Session Handoff

**Updated:** 2026-06-21
**Branch:** main — docs synced + pushed (origin/main = `d646828`); now brainstorming a feature

---

## Active work — auto-populate YAML profile from resume (brainstorming, no code yet)

**Problem found:** the `match_scorer` (and `job_parser`) only see `build_compact_profile`
= `yaml_data` + **first 500 chars of CV** (`profile_builder.py:164`). Uploading a resume
keeps `yaml_data` at the empty starter (`profile.py:170`), so the score is computed
against almost nothing → low score + false `missing_skills`. User chose option 3:
auto-populate the structured profile at upload so all agents benefit.

**Agreed design direction (in brainstorming skill):**
- Auto-populate **`yaml_data`** (not `ProfileReviewData`) from `cv_text` at upload —
  `yaml_data` is in the compact profile, so it directly fixes scoring.
- Make YAML the **single editable surface in the UI for all users** (today `ProfileSetup.tsx`
  shows it read-only); add a per-user YAML save endpoint.
- Remove the structured review form (Projects/Skills, etc.) from the UI; leave the
  `profile_review_data` backend column **dormant** (no migration, minimal blast radius) —
  optional later cleanup.

**Open decision before writing the spec:** extraction mechanism — LLM extractor agent
(recommended: new `profile_extractor`, Haiku, structured YAML output) vs deterministic parser.

**Gotcha noted:** discovery `search_profiles` reads the on-disk `data/candidate_profile.yaml`
(`discovery.py:57`), not per-user `yaml_data` — per-user YAML editing won't change discovery
keywords. Out of scope for the scoring fix; follow-up only.

Next step: finish brainstorming Q (extraction mechanism) → write design doc under
`docs/superpowers/specs/` → writing-plans.

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
