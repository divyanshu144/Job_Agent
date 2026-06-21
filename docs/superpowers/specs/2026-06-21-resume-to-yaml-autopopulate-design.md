# Design: Auto-populate YAML profile from uploaded resume

**Date:** 2026-06-21
**Status:** Approved (brainstorming) — pending spec review
**Author:** pairing session (user + Claude)

## Problem

The `match_scorer` and `job_parser` agents only receive `build_compact_profile`
(`backend/services/profile_builder.py:157`), which is `yaml_data` + the **first
500 characters** of the CV text. Uploading a resume (`POST /profile/cv`,
`routes/profile.py:146`) stores `cv_text` but leaves `yaml_data` at the empty
starter template. Result: the match score is computed against an empty structured
profile plus a 500-char CV snippet, producing a low score and false
`missing_skills` for skills that are actually on the resume.

The user observed this directly: "it only matched score with some of my resume."

## Goal

Auto-populate the structured profile from the uploaded resume so every agent —
the score included — sees the candidate's real skills and experience. Make the
YAML the single editable source of truth in the UI for all users.

## Non-goals (explicit out-of-scope)

- Removing the `ProfileReviewData` schema/column from the backend (left dormant;
  only `links` stays in use). Optional future cleanup.
- Wiring discovery `search_profiles` to read per-user `yaml_data` instead of the
  on-disk `data/candidate_profile.yaml` (`services/discovery.py:57`). Follow-up only.
- Changing `build_compact_profile` itself — not needed once `yaml_data` is filled.

## Key decisions

1. **Target = `yaml_data`** (not `ProfileReviewData`). `yaml_data` is already inside
   `build_compact_profile`, so populating it directly fixes scoring and feeds all agents.
2. **Extraction = a new LLM agent** (`profile_extractor`, Haiku), structured output.
3. **YAML is the single editable surface** in the UI for all users (currently read-only).
4. **Overwrite on every upload**: each CV upload re-runs extraction and replaces
   `yaml_data`. (If the extractor call fails, keep the previous `yaml_data`.)
5. **Form trimmed to Links only**: target_role, key_skills, projects, experience,
   work_preferences all collapse into YAML; the structured form keeps only `links`
   (email/GitHub/LinkedIn/portfolio), because hyperlinks are lost by PDF text
   extraction and links feed resume generation.

## Components

### `ProfileExtractorAgent` (new)
- `backend/agents/profile_extractor.py`, subclass of `BaseAgent`, `model = HAIKU`.
- Prompt: `backend/prompts/profile_extractor.md` ("extract a structured candidate
  profile from this resume text").
- Input: `cv_text`. Output: a Pydantic model `ExtractedProfile` (NOT free-text YAML,
  so the LLM cannot emit malformed YAML), e.g.:
  ```
  ExtractedProfile:
    identity: { name: str, headline: str, location: str }
    core_skills: { languages: list[str], frameworks: list[str], tools: list[str] }
    experience: list[{ company, role, dates, highlights: list[str] }]
    featured_projects: list[{ name, themes: list[str] }]
  ```
- Uses the structured-output path (`_call_structured`) like `match_scorer`.

### YAML serializer (new, small)
- Converts `ExtractedProfile` → YAML string via `yaml.safe_dump`, matching the
  existing schema shape. Does NOT emit `search_profiles` (left to the user/discovery).
- Lives in `backend/services/profile_builder.py`, alongside the other profile-assembly helpers.

## Data flow

### Upload (`POST /profile/cv`)
1. Extract `cv_text` (unchanged).
2. Run `profile_extractor(cv_text)` → `ExtractedProfile` → serialize → YAML string.
3. `build_profile_from_text(yaml_text=<extracted>, cv_text=..., user_id=...)` — replaces
   `yaml_data`; `merged_profile` rebuild + memory re-chunk happen as today.
4. On extractor failure: skip overwrite, keep the user's previous `yaml_data`
   (default if none), store `cv_text`, log a warning. **Upload never 500s on LLM error.**

### Edit (`PUT /profile/yaml`, new)
- Body `{ yaml_text: str }`, auth required (all users).
- Validate it parses with `yaml.safe_load` → 422 with a clear message on failure.
- Persist via `build_profile_from_text` (preserving the user's `cv_text` /
  `profile_review_data`). Returns `ProfileResponse` (existing schema — no drift change).

## Frontend (`frontend/src/pages/ProfileSetup.tsx`)
- Replace the read-only YAML viewer with an editable textarea + Save button
  → `PUT /profile/yaml`; show 422 validation errors inline.
- Trim the review form to the **Links** section only; remove Projects, Skills,
  Experience, Target role, and Work preferences inputs. `ProfileReviewData` TS type
  is unchanged (backend untouched); the UI simply stops editing those fields.

## Error handling
- Extractor LLM failure → warning log, preserve prior YAML, upload succeeds.
- Malformed YAML on `PUT /profile/yaml` → 422, no write.
- Unauthenticated → 401 (existing `get_current_user` dependency).

## Testing (Definition of Done)
- `tests/test_agents/test_profile_extractor.py` — `ExtractedProfile` schema validates
  against a mocked `_call()` response; serializer produces valid, parseable YAML.
- `tests/test_routes/test_profile.py` (extend):
  - upload overwrites `yaml_data` with extracted content (extractor mocked);
  - upload with extractor failure preserves prior YAML and still 200s;
  - `PUT /profile/yaml` happy path persists; 401 without auth; 422 on malformed YAML.
- `make check` green.

## Follow-ups (not in this change)
- Per-user `search_profiles` for discovery keywords.
- Full removal of the dormant `ProfileReviewData` fields (keep `links`).
