# JobFit Agent — Task List

## Pipeline Optimisation (model tiering + split pipeline) — COMPLETE
Full plan: `docs/superpowers/plans/2026-05-23-pipeline-optimisation.md`

- [x] Task 1: Model tiering — base.py + job_parser + match_scorer (Haiku for parsing agents)
- [x] Task 2: Compact profile extraction — build_compact_profile() in profile_builder.py
- [x] Task 3: DB schema — add evaluate_only to Analysis + schemas + migration
- [x] Task 4: Split orchestrator — run_evaluate_pipeline + run_generate_pipeline
- [x] Task 5: Update analyse routes — POST /analyse/generate/{id} endpoint
- [x] Task 6: Frontend types + API client — PipelineDoneData, streamGenerate
- [x] Task 7: Frontend AnalyseJob.tsx — Evaluate → Generate two-phase UI
- [x] Task 8: Frontend Results.tsx — Generate button + placeholder tabs

## Harness Improvements — HANDOFF.md System

- [x] Task 1: Create HANDOFF.md at project root — populate with actual current state (Wave 1 not started, lint failing, tests 131 passing)
- [x] Task 2: Create HANDOFF.template.md at project root — empty template with [bracket] placeholders for all 6 sections
- [x] Task 3: Update CLAUDE.md — add "Session Lifecycle" section with start/checkpoint/end subsections; add HANDOFF.md to session-start read order; define 6 checkpoint triggers
- [x] Task 4: Verify — 131 tests still pass, HANDOFF.md and template exist, CLAUDE.md has new section

## Harness Improvements — Wave 1 (CLAUDE.md drift fixes)

- [x] Task 1: Replace stale project overview TODO with real 3-5 sentence description
- [x] Task 2: Update Architecture Map — add 4 missing routes + 5 missing frontend pages + remove stale TODO comment
- [x] Task 3: Add "Undocumented Conventions" section — 5 items (SSE protocol, _inject vs .replace, with_tracking, runtime model override, JD hash cache limitation)
- [x] Task 4: Add `make check` target to Makefile + update CLAUDE.md Common Commands
- [x] Task 5: Add "Definition of Done" section to CLAUDE.md
- [x] Task 6: Verify — 131 tests still pass, make check runs cleanly

## Referral System (Option B — full tracking)

- [x] Task 1: `models.py` — add `referral_code` (unique, indexed, auto-generated) + `referred_by` (FK → users.id, nullable) to `User`
- [x] Task 2: `database.py` — add `_migrate_add_columns()` helper called from `init_db()` to `ALTER TABLE` add new columns on existing DBs (SQLite has no `ADD COLUMN IF NOT EXISTS`)
- [x] Task 3: `schemas.py` — add `referral_code: str | None = None` to `UserCreate`; add `referral_code: str` to `UserResponse`; add `ReferralEntry` schema `{email, joined_at}`
- [x] Task 4: `routes/auth.py` — update register: accept `referral_code` as alternative to `invite_token` for non-first users; add `GET /api/auth/referrals` returning list of users referred by current user
- [x] Task 5: `types/index.ts` — add `referral_code: string` to `User`; add `ReferralEntry` interface
- [x] Task 6: `api/client.ts` — add `getReferrals()`; update `register()` to accept `referralCode` param
- [x] Task 7: `ProfileSetup.tsx` — add referral section: permanent link (`/register?ref={code}`) with copy button + table of referrals (email, joined date, count badge)
- [x] Task 8: `Register.tsx` — read `?ref=` from URL, pass to register API; show appropriate message when arriving via referral link

## Feature Improvements
Full plan: `docs/superpowers/plans/2026-05-23-feature-improvements.md`

- [ ] Task 1: Analysis caching — jd_hash on Analysis, cache check in run_evaluate_pipeline
- [ ] Task 2: Application tracker (backend) — status column, UpdateStatusRequest, PATCH endpoint
- [ ] Task 3: Application tracker (frontend) — status badges, dropdown, filter in History.tsx
- [ ] Task 4: Recurring gaps dashboard (backend) — InsightGap schema, GET /insights/gaps route
- [ ] Task 5: Recurring gaps dashboard (frontend) — Insights.tsx page, nav item, /insights route
- [ ] Task 6: Cover letter tone picker (backend) — {tone} prompt slot, GenerateRequest, tone param in pipeline
- [ ] Task 7: Cover letter tone picker (frontend) — tone dropdown in AnalyseJob + Results
- [ ] Task 8: Profile compression — _summarise_profile() Haiku call, profile_summary field, use in Phase 1
