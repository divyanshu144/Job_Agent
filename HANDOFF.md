# Session Handoff

**Updated:** 2026-06-07
**Branch:** chore/remove-github-profile-source (off `fix/profile-content-cache-key`)

---

## Current State

**GitHub-as-a-profile-source removal COMPLETE** (plan: `~/.claude/plans/atomic-beaming-hamming.md`,
approved). `make check` green (**234 passed, 76.71% cov**) + `npx tsc --noEmit` clean.

This stacks on the content-hash cache fix (`bd14958`). Removing GitHub is the *deep* fix for the
cache-determinism problem: GitHub READMEs were the only collection-iterating input to
`merged_profile`. With them gone, `merged_profile` is YAML + CV only — deterministic by
construction, so the just-added `sorted()` in `_assemble_merged` was removed (no longer needed),
and the vestigial secondary-1 GitHub-warning block in `_profile_response` is gone too.

**Surface removed:**
- Backend: deleted `services/github_client.py`; `profile_builder.py` (`_assemble_merged`→YAML+CV,
  `_read_repos`→`_read_yaml`, `refresh_github_cache` deleted, no github read in `build_profile`);
  `routes/profile.py` (deleted `/profile/refresh/github` + `/profile/status`, warning block,
  unused imports); `models.py` (`GithubCache`, `Profile.github_data`/`github_last_fetched_at`,
  `UniqueConstraint` import); `config.py` (`github_username`, `github_stale_days`); `schemas.py`
  (`ProfileResponse` github fields, `ProfileStatusResponse`, `GitHubRefreshResponse`).
- Frontend: `ProfileSetup.tsx` (banner, sync timestamp, refresh button, status state, `daysSince`),
  `api/client.ts` (`refreshGithub`, `getProfileStatus` + imports), `types/index.ts` (github fields
  + 2 interfaces).
- Tests: deleted `test_github_client.py`; rewrote merges test to YAML+CV; deleted 2 github
  profile_builder tests; dropped `github_data="{}"` from ~13 fixtures; dropped `github_username`
  from `test_config.py`.
- Docs: `CLAUDE.md` (overview, 2 map lines, JD-hash note), `.env.example` (`GITHUB_USERNAME`).

**Left as-is (per plan):** `scripts/migrate.py` history untouched; orphan `github_cache` table +
`Profile.github_data`/`github_last_fetched_at` columns remain in existing DBs (zero migration,
harmless — SQLAlchemy only queries mapped columns). Optional one-time DROP flagged as follow-up.

## Next Action

Commit on `chore/remove-github-profile-source`. Then fold into the pending batch merge onto `main`
alongside `fix/profile-content-cache-key` (this branch builds on it) and the other feature branches.

## Why It Stopped

Removal complete and verified (backend + frontend). Committing.

## In-Flight

Committing now: `backend/` (config, models, schemas, routes/profile, services/profile_builder,
deleted github_client), `frontend/` (ProfileSetup, client, types), tests (deleted test_github_client,
rewrote test_profile_builder, ~13 fixture edits, test_config), `CLAUDE.md`, `.env.example`,
`tasks/lessons.md`, this HANDOFF.

## Open Questions

1. Optional explicit `DROP TABLE github_cache` + drop the two `Profile` orphan columns on deployed
   DBs — left as a follow-up, not required.
2. Profile row accretion — still leave-as-is (deferred from the cache fix).

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 234 passed, 1 deselected, 76.71% coverage |
| `npx tsc --noEmit` (frontend) | ✓ clean (exit 0) |
