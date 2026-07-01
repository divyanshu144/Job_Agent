# Design: Semantic Stage-1 matching for discovery (Phase 2) + backlog re-score

**Date:** 2026-07-01
**Status:** Approved design, pre-implementation
**Depends on:** Phase 1 (v1.2.0) — discovery reads criteria from the admin's DB profile.
**Scope decision:** Admin-only, consistent with Phase 1 (discovery routes are `require_admin`).

## Problem

Phase 1 fixed the plumbing (discovery now loads the admin's criteria), but discovery's
Stage-1 is a *literal keyword* filter: `_stage1_pass` passes a job only if one of the
`target_roles` strings appears verbatim in the job text. Verified in prod: with valid
criteria set, a remotive run found 31 jobs and passed **0** at Stage-1 — the exact role
phrases ("Backend Engineer", "AI Engineer") did not appear literally. Relevant jobs titled
"Applied Scientist", "ML Engineer", "Full-Stack Developer" are silently dropped.

Separately, ~844 jobs fetched during the pre-v1.2.0 outage are stuck in state `filtered`
(rejected under empty criteria). Discovery dedups on re-fetch, so re-running a source skips
them — they never get re-scored even though many are relevant.

## Goal

Replace the literal keyword Stage-1 with a **semantic gate** (embedding cosine similarity
between the job and the candidate's intent), so discovery matches by meaning. Reuse the
embeddings infra already live in prod (`text-embedding-3-small` + pgvector, verified). Add an
admin-triggered **backlog re-score** that runs the existing `filtered` jobs through the new
gate so the feed populates and the threshold gets calibrated on real data.

## Scope

**In scope**
- Embed each job's `raw_text`; store the vector on the `Job` row (new pgvector column + JSON
  fallback + model tag). Alembic migration.
- Build a candidate **intent vector** from the admin's `target_roles` + `key_skills` +
  identity headline.
- Replace `_stage1_pass` with a semantic gate: `cosine(job, intent) >= threshold`
  (configurable). Keep the location hard-filter and Haiku Stage-2 unchanged.
- Fallback: when embeddings are unavailable (no OpenAI key / embed failure), fall back to the
  existing keyword `_stage1_pass` — same tiered-degradation pattern as `services/memory.py`.
- Admin endpoint `POST /api/discovery/rescore`: re-embed + semantic-gate + Stage-2 + score the
  existing `filtered` jobs against current criteria.

**Out of scope (deferred, tracked)**
- Auto-tuning the threshold; per-user discovery (still admin-only); a job-level semantic
  *search box* (query -> jobs). See "Future work".

## Data model

Add to `Job` (`backend/models.py`), mirroring `MemoryChunk`'s embedding columns:
```python
embedding_json: Mapped[str | None]     # JSON list[float], fallback / non-pgvector read
embedding_model: Mapped[str | None]    # e.g. "text-embedding-3-small"
# embedding_vector pgvector column added via raw SQL in the migration + populated via raw SQL
#   UPDATE ... SET embedding_vector = CAST(:v AS vector), as memory.py does for MemoryChunk.
```
**Alembic migration** (new revision):
- `ALTER TABLE jobs ADD COLUMN embedding_json TEXT`, `embedding_model VARCHAR`.
- `ALTER TABLE jobs ADD COLUMN embedding_vector vector(1536)` guarded by
  `CREATE EXTENSION IF NOT EXISTS vector` (extension already present in prod).
- Migration must be reversible (drop columns in downgrade).
- **This phase requires a manual migration run (`aws-migrate.yml`) before/with deploy.**

## Candidate intent vector

New helper in `backend/services/discovery.py`:
```python
def build_intent_text(profile) -> str:
    """A compact 'what the candidate wants + is' string for embedding: target roles +
    key skills + headline. Empty string when the profile has no signal."""
```
- Source: `parse_profile_review_data(profile.profile_review_data)` -> `target_roles`,
  `key_skills`; plus the `identity.headline` parsed from `profile.yaml_data`.
- Embedded once per run via `embed_texts([intent_text])` (reuse `services/memory.embed_texts`).

## Semantic gate

```python
def semantic_stage1(job_embedding: list[float] | None,
                    intent_embedding: list[float] | None,
                    threshold: float) -> bool | None:
    """True/False when both embeddings exist; None to signal 'embeddings unavailable ->
    caller falls back to keyword _stage1_pass'."""
    if not job_embedding or not intent_embedding:
        return None
    return dense_cosine_similarity(job_embedding, intent_embedding) >= threshold
```
- `dense_cosine_similarity` is reused from `services/memory.py`.
- Caller (`_process_job` and the batch path) computes: `result = semantic_stage1(...)`; if
  `result is None`, use `_stage1_pass(raw_text, profiles)` (keyword fallback); else use it.
- Threshold: new config `settings.discovery_semantic_threshold: float = 0.30` (env
  `DISCOVERY_SEMANTIC_THRESHOLD`). Starting value; calibrated against the 844-job backlog.

## Pipeline composition (the only behavior change)

In `_run_discovery_task` / `_run_source_task` / `_run_batch_discovery_task`, after fetch:
1. Build `intent_text = build_intent_text(profile)`; `intent_emb = embed_texts([intent_text])[0]`
   (or None on failure).
2. Batch-embed fetched job texts: `job_embs = embed_texts([j.raw_text[:2000] for j in raw_jobs])`.
3. Pass each job's embedding + `intent_emb` into `_process_job`, which:
   - keeps the existing **location hard-filter** (`_location_allowed`) as-is,
   - uses `semantic_stage1(...)` in place of `_stage1_pass(...)` (with keyword fallback),
   - stores the job embedding on the `Job` row (raw-SQL pgvector update + `embedding_json`),
   - Stage-2 (Haiku) and scoring unchanged.

`_process_job` gains a `job_embedding: list[float] | None` and `intent_embedding: list[float]
| None` parameter (threaded like `profiles`/`compact` already are).

## Backlog re-score

`POST /api/discovery/rescore` (`routes/discovery.py`, `require_admin`):
- `await _require_search_criteria(db, current_user.id)` (reuse Phase 1 gate).
- Loads jobs in state `filtered` (batched, newest first, capped per call e.g. 500 to bound cost).
- Builds intent from the admin profile; embeds jobs missing an embedding.
- Runs each through `semantic_stage1` -> passers go to Stage-2 + scoring (reusing the same
  internals as `_process_job`, but on existing rows: reset state, no dedup/create step).
- Returns `{rescored, now_scored, still_filtered}` counts.
- Runs as a background task (like discovery runs) so the request returns immediately; progress
  visible via the counts on a follow-up call or a DiscoveryRun-style row.

## Testing (Definition of Done)

- `build_intent_text`: roles + skills + headline; empty when no signal.
- `semantic_stage1`: True/False by threshold; `None` when either embedding missing.
- Fallback: with `embed_texts` patched to return `None`, `_process_job` uses keyword
  `_stage1_pass` (existing behavior preserved).
- Semantic path: with `embed_texts` patched to return vectors and a job embedding close to
  intent, the job passes Stage-1; a distant one is filtered; the job's `embedding_json` is
  persisted.
- Route: `POST /discovery/rescore` requires admin, 422 without criteria, and (mocked
  embeddings + Stage-2 + scoring) moves a `filtered` relevant job to `scored`.
- Migration: upgrade adds the columns; downgrade drops them (mock/skip pgvector in SQLite
  test path — pgvector column addition is Postgres-only, guarded like existing migrations).
- `make check` green (incl. schema-drift if any schema exposed to TS — none expected here).

## Rollout

- **DB migration required** — run `aws-migrate.yml` before/with the deploy (unlike Phases 1).
- After deploy: trigger `POST /discovery/rescore` once to backfill the 844 jobs and calibrate
  the threshold; adjust `DISCOVERY_SEMANTIC_THRESHOLD` if precision/recall is off, then re-run.
- Ships as `v1.3.0`.

## Future work (deferred, tracked)

- Threshold auto-calibration from admin feedback / saved-vs-skipped signal.
- Multi-user discovery + per-user intent vectors (rides on the Phase-1 deferred multi-user work).
- A user-facing semantic job *search box* (`GET /discovery/search?q=` -> pgvector over
  `jobs.embedding_vector`) — now cheap since jobs are embedded.
- pgvector ANN index on `jobs.embedding_vector` if the search box or large re-scores need it.

## Open questions (resolved)

- Candidate vector -> **target_roles + key_skills + headline** (intent), not the 91 memory
  chunks. ✅
- Gate -> **cosine threshold** (configurable), not top-N. ✅
- Semantic **replaces** keyword, keyword is the offline fallback. ✅
- Backlog -> **admin endpoint** `POST /discovery/rescore`, not an auto-migration. ✅
