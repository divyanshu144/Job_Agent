# Session Handoff

**Updated:** 2026-07-02
**`v1.2.0` is LIVE in production.** Phase 2 (semantic matching) is built on branch
`feat/discovery-semantic-matching`, `make check` green (594) — NOT yet merged/deployed.

## In flight: Discovery semantic matching Phase 2 (branch `feat/discovery-semantic-matching`)
Replaces discovery's literal keyword Stage-1 with an embedding cosine gate (job vs. candidate
intent), reusing the live text-embedding-3-small + pgvector infra; adds `POST /api/discovery/rescore`
to re-evaluate the ~844 stuck `filtered` jobs. Verified in prod earlier that the Phase-1 pipeline
scores a fresh relevant job (78) but re-running sources hits dedup — hence the rescore.
- Spec: `docs/superpowers/specs/2026-07-01-discovery-semantic-matching-design.md`
- Plan: `docs/superpowers/plans/2026-07-01-discovery-semantic-matching.md`
- SDD ledger: `.superpowers/sdd/progress.md` (Tasks 1-5 done; Task 4 controller-implemented after
  a subagent session-limit; one item flagged for final review: rescore dedup-hash-rename approach)
- **This phase REQUIRES a DB migration** (0013, pgvector column on `jobs`).
- **Next action:** final whole-branch review → merge → run `aws-migrate.yml` (0013) → tag `v1.3.0`
  → deploy → `POST /api/discovery/rescore` and calibrate `DISCOVERY_SEMANTIC_THRESHOLD` (default 0.30).

## Shipped: Discovery search-criteria Phase 1 (v1.2.0, merged `a4fca24`)
Fixed the prod outage where discovery returned 0 jobs for everyone (no user had `search_profiles`;

## Shipped: Discovery search-criteria Phase 1 (v1.2.0, merged `a4fca24`)
Fixed the prod outage where discovery returned 0 jobs for everyone (no user had `search_profiles`;
the on-disk `data/candidate_profile.yaml` isn't deployed; keyword Stage-1 rejected all jobs).
Admin-only. All 6 plan tasks done + final Opus whole-branch review (READY, no Critical/Important).
**NEXT VERIFY:** discovery still shows 0 until the admin enters roles+locations in the new
Discover "Set up your search" panel, saves, then Fetch. Then confirm jobs actually score.
- Spec: `docs/superpowers/specs/2026-06-27-discovery-search-criteria-onboarding-design.md`
- Plan: `docs/superpowers/plans/2026-06-27-discovery-search-criteria.md`
- SDD ledger: `.superpowers/sdd/progress.md`
- Commits: a0d4c2c (target_roles field) · 34c5ff4 (criteria builder) · 41f448d (user_id threading,
  dropped on-disk file reader) · f498b17 (route 422 gate) · e047d9c (fixed cross-file test
  regressions from the field+signature changes) · 20d1b1e (Discover setup panel + gate)
- **Next action:** optional final whole-branch review; then merge `feat/discovery-search-onboarding`
  -> main + tag `v1.2.0` to deploy. No DB migration (JSON field).
- Deferred & tracked (future phases): semantic Stage-1 matching; multi-user discovery; per-user
  onboarding + feed isolation; campaign wiring. See spec "Future work" + todo.md.
- Minor findings parked for final review are listed in the SDD ledger.

## Previously this session
**`v1.1.1`** shipped the ATS ligature fix (PDF text layer garbled f-ligatures — `fixed`->`xed`;
fixed via glyphtounicode + DisableLigatures in `assets/latex-format.tex`).

## In flight: ATS ligature fix (branch `fix/resume-ats-ligatures`)
**Found by actually rendering a resume + extracting its text** (we'd been fixing blind all
session). The PDF *image* was perfect, but the **text layer garbled f-ligatures** —
`fixed`->`xed`, `flagged`->`agged`, `MLflow`->`MLow`. ATS parsers read the text layer, so they
saw garbage. This is exactly what the user pasted in the very first message (misread then as
truncation). Fix in `assets/latex-format.tex`: `\usepackage{lmodern}` + `\usepackage{microtype}`
+ `\input{glyphtounicode}` + `\pdfgentounicode=1` + `\DisableLigatures`. Verified end-to-end
(rendered rich resume, extracted text — all words clean, 1 page, all content present). Deploy
packages confirmed: microtype ∈ texlive-latex-recommended, lmodern ∈ texlive-fonts-recommended
(both in the Dockerfile backend-tex stage). Guard test added. `make check` green (579 passed).
Repro/verify script: `/tmp/render_sample_resume.py` (PYTHONPATH=. python ...).

**Next action:** merge `fix/resume-ats-ligatures` -> main, tag **`v1.1.1`**, deploy (this is the
deploy that actually fixes real users' resumes). No DB migration.

**Open discussion (not a bug):** user asked whether to use Opus for resume tailoring. Recommended
NO — the resume problems were code/template bugs, not model IQ; Sonnet suits the constrained
tailoring task and matches the user's own routing rule; Opus is ~5x cost on every analysis. If
validating, flip `ResumeTailorerAgent.model = OPUS` and A/B via evals.

---

## Previously this session — v1.1.0 (LIVE)
Prod smoke-tested: frontend 200, `/health` 200, `/api/profile` 401. Merge commit `a7dec74`.
Branch `fix/resume-completeness-education-skills` merged (can be deleted).

---

## In flight (this session): resume "not complete" fix — education + skills authoritative

**Problem diagnosed:** generated resume dropped the education degree and showed only ~5 skills.
Root causes (verified): (1) `resume_latex_template.py` `_limit_words` chops every bullet mid-sentence
to force one page [SEPARATE, not yet fixed]; (2) `validators.py` only accepted the lossy `## CV Text`
blob as evidence, so it deleted the user's real degree and over-pruned skills; (3) education had no
first-class home in the profile schema.

**What this change does (all on disk, uncommitted):** make user-entered/CV-extracted education +
skills authoritative.
- Schema: `ProfileReviewEducation` + `education` on `ProfileReviewData`; `ExtractedEducation` +
  `education` on `ExtractedProfile`.
- Extractor (`prompts/profile_extractor.md`) now pulls education.
- `profile_builder.py`: YAML emits education; `build_profile_review_text` renders an Education
  section; new `review_seed_from_extracted` (flatten skills + education, **non-destructive**).
- `routes/profile.py` `upload_cv`: seeds the review form (draft) from the extraction → autofill.
- **Trust fix** (`validators.py`): skills + degree now validate against the whole profile (YAML +
  Profile Review + CV), not just the CV blob. `_extract_cv_text` → `_evidence_text`.
- `prompts/resume_tailorer.md`: take education from structured profile; broad skills with a floor
  (≥6, aim ≥10); stop collapsing to JD keywords.
- Frontend `ProfileSetup.tsx`: Skills chip input + Education cards + amber "autofilled, review &
  save" draft banner. `types/index.ts` mirrored (schema-drift green).
- `data/candidate_profile.yaml`: added education block — **degrees (MSc/BTech CS) are GUESSED;
  user must confirm/correct** the real degrees.

**Also fixed this session (resume completeness, cause #1 + latent):**
- `resume_latex_template._limit_words` now clips at **sentence boundaries** (drops whole trailing
  sentences; keeps a single over-long sentence whole) — no more "giving the team better." mid-clause.
- `MAX_TOKENS` was one global 4096 output cap; added per-agent `max_output_tokens` (BaseAgent
  default 4096; `ResumeTailorerAgent` + `_ResumeLatexAgent` -> 8192) so rich resumes aren't
  truncated mid-document.

**Header generalization (DONE this session):** `assets/latex-format.tex` hardcoded the admin's
name/contact/links in every user's resume PDF. Replaced with a `%%JOBFIT_HEADER%%` marker built
per-user from `ResumeIdentity` (`resume_identity_from_profile`: YAML identity + review links +
account email; `phone` added to `ExtractedIdentity`/extractor/YAML). `download_resume_pdf` now
passes the user's identity. **Still open:** `campaign_orchestrator._resume_tailor` uses the static
`assets/resume.tex` (the admin's WHOLE resume) via `tailor_resume_pdf` — that path must be routed
through the structured template too (bigger refactor, not just a header).

**Mobile sign-out (DONE this session):** Sign out lived only in the desktop sidebar
(`hidden lg:flex`); the mobile overlay had no logout. Added a user block + Sign out to the mobile
menu (`App.tsx`).

**Branch:** `fix/resume-completeness-education-skills` — pushed (3 commits: education/skills +
truncation fixes, header generalization, mobile sign-out). `make check` green (578 passed).

**Next action (cold-start):** (1) user confirms the guessed degrees in `data/candidate_profile.yaml`;
(2) eyeball ProfileSetup + the mobile menu in a browser (not automated here — env can't host the
app: native PG on :5432 shadows docker + no pgvector); (3) decide deploy (merge to main + tag) vs.
also fixing the campaign `resume.tex` path first; (4) drop the local `jobfit` PG role I created:
`psql -h 127.0.0.1 -U divyanshu -d postgres -c "DROP DATABASE IF EXISTS jobfit; DROP ROLE IF EXISTS jobfit;"`

**Known issues NOT fixed (deliberate — not defects to patch blind):**
- `campaign_orchestrator._resume_tailor` → static `assets/resume.tex` is the admin's whole resume
  for every user's campaign. **DEFERRED (safe): campaigns are not user-available**, so this path
  isn't reachable by real users today — not a live leak. Fix before campaigns are exposed: route
  campaign resume generation through the structured template (`render_resume_pdf` + per-user
  `ResumeIdentity`) instead of editing the static `resume.tex`.
- `discovery.py:11` reads the admin's on-disk `candidate_profile.yaml` `search_profiles` for ALL
  users — multi-tenant gap, but needs a decision on whether discovery is per-user or global first.
- Deferred features: `GET/PATCH /api/campaign/settings`, per-run cost on `CampaignRunResponse`.
- Scaling: rate limiter uses in-memory storage (per-worker limits when multi-worker — needs Redis
  `storage_uri`).
- `ExtractedSkills` has no `ai_llm`/`retrieval` buckets (extractor under-captures AI skills vs the
  hand YAML) — quality gap, not a defect; skills still land under frameworks/tools.

---

## Previous state (v1.0.0 release)

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
