# Agent Memory — Durable Structured Reference

> Companion to `tasks/lessons.md`. lessons.md is the chronological "what broke / what we
> learned" log; this file is the durable **structured reference**. They coexist — don't duplicate.

## Architecture Decisions
<!-- Locked choices. A subagent reading cold must NOT reverse these even if a
     stub's name or surrounding code suggests otherwise. -->
- Drafts-only, no autonomous send. Human-in-the-loop is the feature AND the
  portfolio signal. The campaign orchestrator creates Gmail drafts only. Manual
  per-contact send (/contacts/{id}/send) is human-triggered and fine; NOTHING in
  the autonomous orchestrator may ever call a send path.
- Backend Gmail uses google-api-python-client + OAuth (gmail.compose). NEVER the
  Gmail MCP — MCP is Claude.ai-chat-only, unavailable server-side.
- Campaign orchestrator: each job gets its own AsyncSession (never shared across
  jobs). Sequential steps within one job may share that job's session.
- Artifact flow: PDF threads resume_tailor -> draft_create directly. It does NOT
  pass through cold_email (cold_email returns body text only).
- Postgres everywhere; SQLite + aiosqlite fully retired. Tests run on
  testcontainers Postgres.
- All timestamp columns are timestamptz (DateTime(timezone=True)); _utcnow()
  stays tz-aware UTC. Forced by correctness, not optional.
- Alembic is the single source of truth for schema. create_all is confined to
  the test fixture. [SHIPPED] App boot detects a complete pre-Alembic schema
  with no alembic_version, stamps head, then runs `alembic upgrade head`.
  Transitional local-volume bridge only; fresh DBs created by migrations never
  hit the stamp branch.
- FK enforcement ON by default in tests (prod-parity). @pytest.mark.relaxed_fks
  is the sanctioned escape hatch and is used by zero tests.
- OUT of scope (do not implement without explicit approval): JSON->JSONB,
  connection-pool tuning, multi-domain support, prompt caching (dormant below
  the cacheable-prefix threshold).
- Job sources: Reed, Adzuna, HN, Remotive, plus Greenhouse/Lever/Ashby via
  assets/target_companies.json. RULED OUT: LinkedIn, Indeed, Wellfound
  (ToS/fragility/Selenium). YC v0.1 companies API dropped (exposes no ATS link).
- Admin enforcement: require_admin dependency (server-side, never UI-only)
  gates discovery, campaign, cost/telemetry, contact-discovery, cold-email,
  and Gmail-draft routes. Regular tier (any authenticated user): analysis,
  score, gaps, cover letter, resume tailoring (interactive), resume .docx
  download, profile. is_admin on User — first registered user is admin.
- Pipeline retry: JobResult is one row per (analysis, agent) enforced by
  upsert. to_user_error() is the sole boundary — raw str(exc) never reaches
  JobResult.error, SSE, or result_errors. Retry never re-runs a succeeded
  step (scope=failed default). Analysis.retry_running_at is the concurrency
  claim (conditional UPDATE, not in-process lock). run_steps() is the single
  runner for both phases.

## Known Gotchas
- Phase-2 gather: narrow BaseException → Exception but explicitly re-raise
  KeyboardInterrupt and SystemExit before the catch — swallowing those causes
  silent hangs on shutdown.
- asyncpg rejects tz-aware datetimes into a non-tz (timestamp WITHOUT time zone)
  column; SQLite silently accepted them. Use timestamptz.
- Greenhouse: legacy boards.greenhouse.io/{slug}/jobs.json 404s. Use
  boards-api.greenhouse.io/v1/boards/{slug}/jobs; content is HTML-escaped, so
  unescape -> strip before storing.
- SQLite silently accepts dangling FKs; Postgres enforces them. Migrating
  surfaces hidden test-seed debt — seed FK-valid parents via factories.
- Alembic upgrade-from-empty must create tables in FK-dependency order (jobs
  before campaign_jobs) or Postgres errors "relation does not exist".
- init_db PRAGMA table_info / ALTER TABLE ADD COLUMN is SQLite-only — hard syntax
  error on Postgres. Alembic owns migrations now.
- pdflatex needs texlive on PATH for real runs; mock the subprocess in tests.
- Haiku's real minimum cacheable prefix is 4096 tokens, not the documented 2048
  (verified empirically against the live API).
- alembic/env.py calls asyncio.run() internally (run_migrations_online). Calling
  command.upgrade() from inside a running event loop (e.g. a FastAPI lifespan)
  raises RuntimeError: asyncio.run() cannot be called from a running event loop.
  Fix: extract a sync _run_upgrade(url) helper and call it via
  await asyncio.to_thread(_run_upgrade, url) — the thread has no running loop,
  so alembic's asyncio.run() proceeds normally. Docker/Uvicorn needs a second
  guard: force asyncio.DefaultEventLoopPolicy() around the Alembic commands and
  restore the previous policy after. to_thread alone was not enough in the
  uvicorn[standard] container context.

## Solved Problems
- Rotating uuid4() in the cache key made sha256(jd::profile.id) unstable. Fix:
  profile_content_hash(merged_profile) + a unified analysis_cache_key() helper.
- Non-deterministic merged_profile from unordered dict iteration. Fix: removed
  GitHub integration entirely (root-cause elimination beat patching ordering).
- Stale test fixtures during merges (a test built Profile(github_data=...) after
  that field was removed). Caught by running make check after EACH merge.
- _record_failure created duplicate CampaignJob rows when a job errored after
  being queued. Fix: made it an upsert.

## Useful Patterns
- Test DB isolation: session-scoped testcontainers Postgres; per-test
  connection-level transaction + nested SAVEPOINT, roll back after each test
  (SQLAlchemy "join an external transaction"). Do NOT recreate schema or truncate
  per test.
- tests/factories.py: make_user/make_profile/make_analysis/make_discovery_run/
  make_job seed FK-valid parents + flush.
- Route-created profile snapshots that must be visible to a later request need
  an explicit commit. Returning a flushed-but-uncommitted Profile from one
  request can make the next request create or select a different bootstrap row.
- pdflatex self-correction: on non-zero exit, retry once feeding the log tail
  into the correction prompt; raise on the second failure.
- Orchestrator resilience: per-job try/except — one job failing logs and the run
  continues; never abort the batch.
- Validate a live endpoint's response shape before building an orchestrator on an
  external API (caught both the YC and Greenhouse issues pre-ship).
- BaseAgent._call_structured self-corrects once on invalid_output
  (JSONDecodeError / ValidationError / parse-AgentError): re-calls with the
  validation error + prior_raw[:500] fed back; hard cap 2 calls total.
  Transient errors (rate_limited, timeout) bypass it entirely — SDK owns those.
  resource_planner excluded (bespoke accounting). AgentError + _parse_json now
  live in base.py; job_parser.py re-exports them for back-compat.
