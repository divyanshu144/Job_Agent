# TODO

## ACTIVE: CV-autofilled, user-confirmed education + skills (authoritative)

Goal: upload CV -> extractor fills education + skills -> draft pre-fills the UI form ->
user edits/confirms -> confirmed data is authoritative for the resume (no more nulled
degree / over-pruned skills). Supersedes the "remove dormant ProfileReviewData fields"
candidate below — we revive key_skills and add education.

### Backend
- [x] schemas.py: ProfileReviewEducation + education on ProfileReviewData; ExtractedEducation + education on ExtractedProfile
- [x] prompts/profile_extractor.md: extract education; update output JSON schema
- [x] profile_builder.py: extracted_profile_to_yaml emits education
- [x] profile_builder.py: build_profile_review_text renders Education section
- [x] profile_builder.py: ExtractedProfile -> review-seed mapper (key_skills flattened, education), non-destructive
- [x] routes/profile.py upload_cv: seed profile_review_data (draft) from extraction
- [x] evals/validators.py: skills + degree validate against whole profile (YAML + Review + CV), not just ## CV Text
- [x] prompts/resume_tailorer.md: education from structured profile; broad skills with floor
- [x] data/candidate_profile.yaml: add education block (admin parity) — DEGREES GUESSED, user to confirm

### Frontend (frontend-design skill)
- [x] types/index.ts: mirror ProfileReviewEducation + education (schema-drift)
- [x] ProfileSetup.tsx: Skills chip input + Education cards + "autofilled, review & save" draft banner

### Verification (Definition of Done)
- [x] Tests: extractor education; review-seed mapper; build_profile_review_text education; validator keeps review-backed degree/skill; PUT /profile/review + upload_cv round-trip education
- [x] make check green (fmt + lint + schema-drift + tests) — 567 passed, 83% cov
- [x] Update HANDOFF.md
- [ ] Manual: render ProfileSetup in browser to confirm new sections look right (not automated)
- [x] BUG: resume_latex_template.py _limit_words chopped bullets mid-sentence — now clips at sentence boundaries
- [x] BUG (latent): global MAX_TOKENS=4096 truncated big resumes — per-agent max_output_tokens (resume agents -> 8192)
- [x] BUG: resume PDF header hardcoded admin identity (latex-format.tex) — now per-user via %%JOBFIT_HEADER%% + ResumeIdentity
- [x] BUG: mobile menu had no Sign out (only desktop sidebar) — added to mobile overlay
- [ ] DEFERRED (campaigns not user-available): route campaign resume gen through the structured
      template instead of static assets/resume.tex (currently the admin's whole resume)

### Decisions locked
- Education fields: institution, degree, field_of_study, dates
- Skills autofill: flatten extractor skill buckets into key_skills; non-destructive on re-upload
- Validator: trust user-entered (Profile Review) data as evidence; still block pure inventions

---

> Snapshot reset 2026-06-21. The FDE-readiness goal (5 tasks) and the multi-tenant
> campaign feature are complete and shipped (history through `87117f2`); the prior
> detailed checklist is preserved in git history. Deployment/infra work since then
> is also shipped (see HANDOFF.md for the commit-by-commit breakdown).

## Done (shipped on main)

- [x] FDE readiness: health/metrics, agent retry+breaker, campaign UI, consistency evals, rate limiting
- [x] Multi-tenant campaign system (backend units 1–6 + frontend) + two review rounds + cleanup pass
- [x] Docker (multi-stage) + docker-compose + prod override + local Kubernetes manifests
- [x] CI: `make check` + Docker image build/smoke workflows
- [x] AWS ECS Fargate deployment (`deploy-aws.yml`, `aws-migrate.yml`, `infra/aws/` task defs); RDS + ElastiCache
- [x] OpenAI semantic embeddings + pgvector with keyword fallback (`services/memory.py`)
- [x] Resume PDF tooling: dedicated `backend-tex` Docker stage (api+worker only)
- [x] Docs sync (CLAUDE.md / README.md / HANDOFF.md / todo.md) to current architecture
- [x] **Resume → YAML auto-populate** feature (extractor agent, PUT /profile/yaml, UI) — `v1.0.0`
- [x] Dockerfile texlive layer-order fix (texlive cached across backend code changes) — `dad30a3`
- [x] Dropped redundant `chown -R /app` in the tex stage — `dad30a3`
- [x] CORS cutover to `https://app.jobfitapp.uk` (committed task-defs + deployed) — `fb63edc`
- [x] Deploy hardening: tag-based trigger + concurrency guard; ECS circuit breaker + rollback;
      beat singleton (min 0/max 100, AZ rebalancing off); documented in `infra/aws/README.md`
- [x] **Cut `v1.0.0` release tag + deploy** — live, prod smoke-tested at `app.jobfitapp.uk`

## ACTIVE spec: Admin job-search criteria for discovery (Phase 1)
Spec: `docs/superpowers/specs/2026-06-27-discovery-search-criteria-onboarding-design.md`
Fixes prod outage: discovery returns 0 for everyone (no search criteria source exists —
on-disk yaml not in image; no DB profile has search_profiles). Admin-only for now.
- [ ] Add `target_roles` to `ProfileReviewData` (+ TS mirror)
- [ ] Discovery reads criteria from admin's DB profile (drop on-disk file dependency); gate with 4xx when missing
- [ ] Discover-page "Set up your search" panel (roles + locations required) + empty-state gate
- [ ] Tests + make check; ship as `v1.2.0`

### Deferred & TRACKED (not dropped) — future discovery phases
- [ ] Phase 2: semantic Stage-1 matching (embed profile <-> job for recall)
- [ ] Multi-user discovery (open beyond admin; remove require_admin where appropriate)
- [ ] Per-user onboarding (guided first-run step gating discovery until roles+locations set)
- [ ] Per-user feed isolation (per-(user,job) relevance; jobs table currently global, single relevance_score)
- [ ] Campaign: point at the same criteria source when campaigns go user-available

## Open / candidate (not committed to)

- [ ] Wire discovery `search_profiles` to per-user `yaml_data` (today reads on-disk
      `data/candidate_profile.yaml`, `discovery.py:57`)  ← SUPERSEDED by the ACTIVE spec above
- [ ] Remove the dormant non-`links` `ProfileReviewData` fields (kept `links`)
- [ ] `GET/PATCH /api/campaign/settings` route pair (enabled toggle + caps display)
- [ ] Per-run cost on `CampaignRunResponse`
- [ ] Redis `storage_uri` for the rate limiter when going multi-worker
