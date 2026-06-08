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

## Harness Improvements — Wave 2 (Git Safety Skills)

- [x] Task 1: Create `.claude/skills/git-leak-cleanup.md` — generic skill: scrub secrets from git history with git-filter-repo, rotate credentials, force-push safely
- [x] Task 2: Create `.claude/skills/pre-push-checklist.md` — lightweight companion skill: pre-push safety checklist (secrets scan, large files, sensitive paths)
- [x] Task 3: Update `RESOLVER.md` — add routing rows for both new skills (`leak`, `secret`, `credential`, `history`, `filter-repo` → git-leak-cleanup; `push`, `pre-push`, `safe to ship` → pre-push-checklist)
- [x] Task 4: Run `make check` — verify no regressions introduced (lint baseline unchanged, tests still pass)
- [x] Task 5: Update `HANDOFF.md` — Current State = two new skills added; Next Action = Feature Improvements wave (Task 1: analysis caching); In-Flight = None

**Constraint:** Do NOT touch `backend/`, `frontend/`, or `tests/` files.

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

## Observability & Instrumentation
Full plan: `~/.claude/plans/atomic-beaming-hamming.md` (approved 2026-06-01)

### Wave 5 — Docs correction (first)
- [x] Correct `observability-audit.md` #8 (evals scaffolded-but-lost) + Open Question (pipeline_events growth)

### Wave 0 — Foundation: structured logging keyed on trace_id
- [x] `trace_id_var` contextvar + `new_trace_id()`/`get_trace_id()` (instrumentation.py)
- [x] JSON log formatter + trace_id filter; `configure_logging()` + `log_level` (config.py); call in main.py lifespan

### Wave 1 — Events table + write helper
- [x] `PipelineEvent` model + index on (trace_id, kind); `log_event()` (fail-open) + `span()` ctx manager

### Wave 2 — Stamp signals
- [x] trace_id at entry points; per-agent spans; failure capture + JobResult.error; tool-call logs (discovery fetches); explicit max_retries
- [ ] (deferred) tool-call logs for contact_discovery / github_client (non-pipeline paths)

### Wave 3 — Unify ids
- [x] trace_id in logs + every event; events carry analysis_id/run_id to join LLMCall (satisfied by design)

### Wave 4 — Feedback track
- [x] `Feedback` model + schemas + `routes/feedback.py` + register; frontend thumbs control; `backend/evals/__init__.py` hook stub

## Analysed-jobs list (A scope: visibility only — surfaced on Analyse page)
Plan: `~/.claude/plans/atomic-beaming-hamming.md` (approved 2026-06-02)
- [x] Denormalize role_type/company/match_score onto Analysis (+ init_db ALTER migration)
- [x] Populate at write-time in run_evaluate_pipeline; AnalysisSummary + TS type gain the fields
- [x] `scripts/backfill_analysis_meta.py` (backfill meta + `--claim-orphans`) — USER runs it
- [x] `api.listHistory`; list rendered on `AnalyseJob.tsx` (loaded on mount, refreshed after analyse).
      NO separate page/route/nav (per user: visible on Analyse page only).
- [x] Tests: history endpoint (meta + auth), orchestrator denorm, backfill script. make check green (185)
- [ ] (user) run backfill against data/jobfit.db to recover the 4 rows (2 owned + 2 orphaned)
- [ ] (deferred B) status/application-stage UI + filters

## Deferred / Backlog (flagged — revisit later)
- [ ] **App startup schema strategy** (post Postgres migration, PR #11): `init_db()` still uses
      `Base.metadata.create_all` at boot; Alembic is the source of truth for explicit migrations.
      Decide whether startup should run `alembic upgrade head` instead of (or before) `create_all`.
      Non-blocking — flagged 2026-06-08.
