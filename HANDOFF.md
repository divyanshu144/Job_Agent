# Session Handoff

**Updated:** 2026-06-06  
**Branch:** fix/profile-content-cache-key (off `main` `f571595`)

---

## Current State

**Profile-cache correctness fix COMPLETE** (plan: `~/.claude/plans/atomic-beaming-hamming.md`,
approved). TDD throughout; `make check` green (**238 passed, 75.74% cov**).

**Primary (cache keyed on rotating id → content-hash):**
- `build_profile` inserts a fresh `uuid4()` Profile row every build, so the old key
  `sha256(jd :: profile.id)` invalidated the whole analysis cache on every Refresh/CV/GitHub.
- Added one primitive `profile_content_hash(merged_profile)` (`profile_builder.py`) and one helper
  `analysis_cache_key(jd, profile)` (`orchestrator.py`); both cache sites (`run_evaluate_pipeline`,
  `_run_phase1`) now derive the key through it. Content-addressed: identical content survives a
  Refresh; changed content invalidates. No DB migration (`jd_hash` column unchanged); existing
  `jd_hash` values go permanently un-hit — expected one-time cold start, not a regression.

**Secondary 1 (GitHub-warning divergence — fixed):** `build_profile` now filters empty-content cache
rows out of `github_readmes`/`github_data`, and `_profile_response` warns off empty `github_data`
(not the timestamp). Both derive from one signal: "is there real GitHub content."

**Secondary 2 (profile row accretion):** investigated, **left as-is** (recommended) — with the
content-hash fix it no longer affects cache correctness, and `Analysis.profile_id` FKs to old
`profiles.id` so pruning/upsert would orphan history. Flagged as future work; not changed.

**Docs corrected:** CLAUDE.md JD-hash note (content-hash behavior) + map label
("YAML editor" → "read-only YAML viewer"); `tasks/lessons.md` 2026-05-26 cache entry superseded
(root cause: "rotating identifier as a proxy for content in a cache key").

**Tests:** `tests/test_orchestrator/test_cache_key.py` (new, 3), `test_analysis_caching.py`
(updated to content-hash + id-rotation regression test), `test_profile_builder.py` (empty-README
→ no-GitHub warning).

## Next Action

Branch is ready to commit/push and fold into the pending batch merge onto `main` (alongside
`fix/drop-ineffective-prompt-cache`, `feat/resource-planner-selfcheck`, `feat/discovery-improvements`,
`docs/project-patterns`). No frontend code touched (the YAML-editor fix is a doc) → no `tsc` needed.

## Why It Stopped

Fix complete and verified. Committing.

## In-Flight

Committing now on `fix/profile-content-cache-key`: `profile_builder.py`, `orchestrator.py`,
`routes/profile.py`, `CLAUDE.md`, `tasks/lessons.md`, this HANDOFF, + the three test files.

## Open Questions

1. Profile row accretion — leave-as-is (current) vs prune-to-last-N vs upsert-canonical (needs a
   `Analysis.profile_id` repoint migration). Deferred.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 238 passed, 1 deselected, 75.74% coverage |
| new/updated tests | ✓ cache-key content-addressing, id-rotation regression, empty-README warning |
