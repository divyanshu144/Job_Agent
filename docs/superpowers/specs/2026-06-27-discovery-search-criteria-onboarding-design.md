# Design: Guided job-search onboarding + per-user discovery criteria (Phase 1)

**Date:** 2026-06-27
**Status:** Approved design, pre-implementation
**Author:** pairing session (Divyanshu + Claude)

## Problem

Discovery returns **0 jobs for every user** in production (verified: 6 users, 18
profiles, last run 661 found → 0 keyword → 0 scored). Root cause is not a single bug but
a missing input:

- `discovery._load_search_profiles()` reads `search_profiles` from the on-disk
  `data/candidate_profile.yaml`, which is **deliberately excluded** from the image
  (`.dockerignore` / `.gitignore` — "local data the image must never bake in"). In the
  container the file does not exist → returns `[]`.
- No DB profile contains `search_profiles`/`target_roles` either: the CV extractor does
  not generate them (`extracted_profile_to_yaml` docstring: "left to the user/discovery"),
  and users never hand-author them.
- `_stage1_pass` = "does any configured `target_role` literally appear in the job text".
  With an empty role list this is `any([])` = **False for every job** → all jobs land in
  state `filtered` → 0 scored → empty feed.

There is simply **no source of "what is this user looking for."** The CV tells us who they
are (skills/history); it does not tell us which roles/locations they want.

## Goal

Collect the minimum search intent from each user via a guided onboarding step, store it
per-user, and make discovery read it from the database (not the file). This unblocks
discovery for real users and replaces the misleading empty state.

Semantic matching (embedding profile ↔ job for recall) is the **Phase 2** follow-up and is
explicitly **out of scope here**; Phase 1 keeps the existing keyword gate, now fed real
criteria.

## Scope

**In scope (Phase 1)**
- New required search criteria (target roles + locations) collected via a guided step.
- Persist on the existing per-user `ProfileReviewData` (reuse `work_preferences.locations`;
  add a clean `target_roles` field).
- Discovery builds its `SearchProfile` from the triggering user's DB profile, not the file.
- Discovery scoped to the triggering user.
- Clear "set up your job search" gate/empty state on Discover when criteria are missing.

**Out of scope (later)**
- Phase 2 semantic Stage-1 matching (separate spec).
- Per-user feed isolation (jobs table stays global; `relevance_score` stays single-valued,
  scored against the triggering user — acceptable while discovery is admin/operator-driven).
- Campaign enablement (campaigns are not user-available today). Campaign will read the same
  criteria source when it is exposed; no campaign UI work here.

## Data model

Add one field to `ProfileReviewData` (schemas.py), mirrored in `frontend/src/types`:

```python
class ProfileReviewData(BaseModel):
    ...
    target_roles: list[str] = Field(default_factory=list)   # NEW
    # existing: work_preferences.locations, work_preferences.remote
```

- Locations + remote already exist on `work_preferences`; reuse them.
- `target_roles` is added explicitly rather than overloading the ambiguous `role_types`
  (which reads as employment type, not job titles).
- No new table, no DB migration: `profile_review_data` is a JSON/text column, so the new
  field rides inside it (same as the education work).
- Schema-drift check (`scripts/check_schema_drift.py`, run in `make lint`) requires the TS
  mirror to be updated in lockstep.

## Deriving discovery criteria from the profile

New helper (e.g. `discovery.search_profiles_for_profile(profile) -> list[SearchProfile]`):
- Parse the user's `ProfileReviewData`.
- Build a single `SearchProfile` named e.g. `"my-search"` with:
  - `target_roles` = `review.target_roles`
  - `allowed_locations` = `review.work_preferences.locations` (+ `"Remote"` if remote set)
  - `min_score` = default constant (e.g. `DISCOVERY_DEFAULT_MIN_SCORE = 60`)
- Returns `[]` when roles or locations are empty → callers treat this as "not configured".

`_load_search_profiles()` (the file reader) is replaced at its call sites by this
profile-sourced builder. The file path / starter-yaml fallback is removed from the
discovery path.

## Backend wiring

- `routes/discovery.py` (`POST /discovery/run`, `/run/all`) already has `current_user`.
  - Load the user's owned profile (`get_owned_profile`).
  - Build criteria via the helper.
  - If criteria are empty → **return a clear 4xx** (`{"detail": "Set up your job search
    first — add target roles and locations."}`) instead of starting a run that scores 0.
  - Otherwise pass the criteria into the discovery run.
- `services/discovery.py`: thread `criteria: list[SearchProfile]` (and `user_id`) through
  `run_discovery`, `_run_discovery_task`, `_run_source_task`, `_process_job`, and the batch
  path, replacing every `_load_search_profiles()` call. `_stage1_pass`, `_location_allowed`,
  `_match_profiles` already take `profiles` — pass the per-user list.
- `Job.matched_profiles` stores the synthesized profile name(s) as today.

## Frontend

- **Onboarding step** ("Set up your job search"): one short screen.
  - Target roles — chip input, **≥1 required**.
  - Locations — chip input with a "Remote" chip, **≥1 required**.
  - Optional: remote-only toggle, seniority (deferred if it adds noise).
  - Saves via existing `PUT /profile/review` (now including `target_roles`).
- **Gate / empty states:** Discover (and Campaign, read-only note) detect missing criteria
  and render a "Tell us what you're looking for → Set up your search" CTA routing to the
  step. Replaces the current `0`-with-"edit data/candidate_profile.yaml" message.
- Reuse the existing chip-input pattern from the skills/education work for consistency.

## Validation & errors

- Server-side: discovery endpoints reject when `target_roles` or `locations` is empty, with
  an actionable message (no silent empty run).
- Client-side: onboarding step disables submit until both required fields have ≥1 entry.

## Testing (Definition of Done)

- `schemas`: `ProfileReviewData` round-trips `target_roles`.
- `search_profiles_for_profile`: builds a SearchProfile from roles+locations; returns `[]`
  when either is missing; adds "Remote" when remote set.
- `routes/discovery`: `POST /discovery/run` returns the actionable 4xx when criteria are
  missing; happy path runs when criteria exist (mocked fetch/score); auth required.
- `routes/profile`: `PUT /profile/review` persists `target_roles` (extend existing test).
- Discovery unit: `_stage1_pass` passes a job when a target role matches the per-user
  criteria (no dependency on the on-disk file).
- `make check` green (fmt + lint + schema-drift + tests).
- Frontend typecheck + build pass.

## Rollout

- No DB migration (JSON field).
- After deploy, existing users will see the "set up your job search" gate until they fill it
  — expected and correct (they currently have no criteria).
- Ships as its own tag (e.g. `v1.2.0`).

## Open questions (resolved)

- Field vs reuse → **add `target_roles`** (avoid `role_types` ambiguity). ✅
- Slicing → **Phase 1 (this spec) first**, semantic matching as a separate spec. ✅
- Onboarding form vs settings panel → **guided step**, with roles + locations **required**. ✅
