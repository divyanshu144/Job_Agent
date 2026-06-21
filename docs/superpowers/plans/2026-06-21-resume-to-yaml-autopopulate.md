# Resume → YAML Auto-Populate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-populate the per-user `yaml_data` profile from an uploaded resume (via a new LLM extractor agent) and make YAML the single editable profile surface in the UI for all users, so the match score and every agent see the candidate's real skills/experience.

**Architecture:** A new `ProfileExtractorAgent` (Haiku) turns `cv_text` into a structured `ExtractedProfile` Pydantic model, which a serializer converts to YAML. `POST /profile/cv` runs it on every upload and overwrites `yaml_data` (preserving the prior YAML only if extraction raises). A new `PUT /profile/yaml` lets any authenticated user edit their YAML (validated). The frontend exposes an editable YAML textarea and trims the structured form to the Links section only. `ProfileReviewData` stays in the backend but only `links` remains in use.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 async, Anthropic SDK, pyyaml; React 19 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-06-21-resume-to-yaml-autopopulate-design.md`

---

## File Structure

- **Create** `backend/agents/profile_extractor.py` — the extractor agent (one responsibility: cv_text → `ExtractedProfile`).
- **Create** `backend/prompts/profile_extractor.md` — the extractor prompt.
- **Modify** `backend/schemas.py` — add `ExtractedProfile` (+ nested models) and `ProfileYamlUpdate`.
- **Modify** `backend/services/profile_builder.py` — add `extracted_profile_to_yaml()`.
- **Modify** `backend/routes/profile.py` — run extractor in `upload_cv`; add `PUT /profile/yaml`.
- **Create** `tests/test_agents/test_profile_extractor.py` — agent + serializer tests.
- **Modify** `tests/test_routes/test_profile.py` — upload-populates / upload-failure-preserves / yaml-edit tests.
- **Modify** `frontend/src/api/client.ts` — add `saveProfileYaml`.
- **Modify** `frontend/src/pages/ProfileSetup.tsx` — editable YAML for all users; form trimmed to Links.

---

## Task 1: `ExtractedProfile` schema + YAML serializer

**Files:**
- Modify: `backend/schemas.py` (add models near the other Profile* models, ~line 155)
- Modify: `backend/services/profile_builder.py` (add serializer after `build_compact_profile`, ~line 165)
- Test: `tests/test_agents/test_profile_extractor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents/test_profile_extractor.py` (all imports at the top — Task 2 appends only functions, so include `json`/`patch`/`pytest` now to avoid ruff E402):

```python
import json
from unittest.mock import patch

import pytest
import yaml

from backend.schemas import ExtractedProfile
from backend.services.profile_builder import extracted_profile_to_yaml


def test_extracted_profile_to_yaml_roundtrips_into_schema_shape():
    profile = ExtractedProfile.model_validate(
        {
            "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
            "core_skills": {
                "languages": ["Python", "SQL"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
            },
            "experience": [
                {
                    "company": "Analytical Engines",
                    "role": "Engineer",
                    "dates": "2023-2025",
                    "highlights": ["Built the first algorithm"],
                }
            ],
            "featured_projects": [{"name": "Note G", "themes": ["computation"]}],
        }
    )

    text = extracted_profile_to_yaml(profile)
    loaded = yaml.safe_load(text)

    assert loaded["identity"]["name"] == "Ada Lovelace"
    assert loaded["core_skills"]["languages"] == ["Python", "SQL"]
    assert loaded["experience"][0]["company"] == "Analytical Engines"
    assert loaded["featured_projects"][0]["name"] == "Note G"
    # Must NOT invent search_profiles (left to the user / discovery).
    assert "search_profiles" not in loaded


def test_extracted_profile_to_yaml_handles_empty_profile():
    text = extracted_profile_to_yaml(ExtractedProfile())
    loaded = yaml.safe_load(text)
    assert loaded["identity"]["name"] == ""
    assert loaded["core_skills"]["languages"] == []
    assert loaded["experience"] == []
    assert loaded["featured_projects"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agents/test_profile_extractor.py -v`
Expected: FAIL — `ImportError: cannot import name 'ExtractedProfile'`

- [ ] **Step 3: Add the schema to `backend/schemas.py`**

Insert immediately after `class ProfileReviewData(...)` (before `class PriorOutputs`):

```python
class ExtractedIdentity(BaseModel):
    name: str = ""
    headline: str = ""
    location: str = ""


class ExtractedSkills(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ExtractedExperience(BaseModel):
    company: str = ""
    role: str = ""
    dates: str = ""
    highlights: list[str] = Field(default_factory=list)


class ExtractedProject(BaseModel):
    name: str = ""
    themes: list[str] = Field(default_factory=list)


class ExtractedProfile(BaseModel):
    """Structured candidate profile extracted from resume text by profile_extractor.
    Serialized to YAML (extracted_profile_to_yaml) to populate Profile.yaml_data."""

    identity: ExtractedIdentity = Field(default_factory=ExtractedIdentity)
    core_skills: ExtractedSkills = Field(default_factory=ExtractedSkills)
    experience: list[ExtractedExperience] = Field(default_factory=list)
    featured_projects: list[ExtractedProject] = Field(default_factory=list)
```

(`BaseModel` and `Field` are already imported in `schemas.py`.)

- [ ] **Step 4: Add the serializer to `backend/services/profile_builder.py`**

Add `import yaml` to the top imports block, then add this function after `build_compact_profile`:

```python
def extracted_profile_to_yaml(profile: ExtractedProfile) -> str:
    """Render an ExtractedProfile as YAML matching the candidate_profile schema.
    Does NOT emit search_profiles — that is left to the user/discovery."""
    data = {
        "identity": {
            "name": profile.identity.name,
            "headline": profile.identity.headline,
            "location": profile.identity.location,
        },
        "core_skills": {
            "languages": list(profile.core_skills.languages),
            "frameworks": list(profile.core_skills.frameworks),
            "tools": list(profile.core_skills.tools),
        },
        "experience": [
            {
                "company": e.company,
                "role": e.role,
                "dates": e.dates,
                "highlights": list(e.highlights),
            }
            for e in profile.experience
        ],
        "featured_projects": [
            {"name": p.name, "themes": list(p.themes)} for p in profile.featured_projects
        ],
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
```

Add the import for the type at the top of `profile_builder.py` (it already imports from `backend.schemas`):

```python
from backend.schemas import ExtractedProfile, ProfileReviewData
```

(Update the existing `from backend.schemas import ProfileReviewData` line to include `ExtractedProfile`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_agents/test_profile_extractor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/services/profile_builder.py tests/test_agents/test_profile_extractor.py
git commit -m "feat(profile): ExtractedProfile schema + YAML serializer"
```

---

## Task 2: `ProfileExtractorAgent` + prompt

**Files:**
- Create: `backend/agents/profile_extractor.py`
- Create: `backend/prompts/profile_extractor.md`
- Test: `tests/test_agents/test_profile_extractor.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agents/test_profile_extractor.py` (functions only — imports already at the top from Task 1):

```python
HAPPY_EXTRACT = json.dumps(
    {
        "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
        "core_skills": {"languages": ["Python"], "frameworks": ["FastAPI"], "tools": ["Docker"]},
        "experience": [
            {"company": "Acme", "role": "Engineer", "dates": "2023", "highlights": ["Shipped X"]}
        ],
        "featured_projects": [{"name": "JobFit", "themes": ["LLM"]}],
    }
)


async def test_profile_extractor_happy_path():
    from backend.agents.profile_extractor import ProfileExtractorAgent

    async def _call(self, s, u):
        return HAPPY_EXTRACT

    with patch.object(ProfileExtractorAgent, "_call", new=_call):
        result = await ProfileExtractorAgent().run("Ada Lovelace, ML Engineer, Python, FastAPI...")

    assert isinstance(result, ExtractedProfile)
    assert result.identity.name == "Ada Lovelace"
    assert result.core_skills.languages == ["Python"]
    assert result.experience[0].company == "Acme"


async def test_profile_extractor_uses_haiku():
    from backend.agents.base import HAIKU
    from backend.agents.profile_extractor import ProfileExtractorAgent

    assert ProfileExtractorAgent.model == HAIKU


@pytest.mark.parametrize("bad", ["not json", json.dumps({"identity": "wrong-type"})])
async def test_profile_extractor_malformed_raises(bad):
    from backend.agents.base import AgentError
    from backend.agents.profile_extractor import ProfileExtractorAgent

    async def _call(self, s, u):
        return bad

    with patch.object(ProfileExtractorAgent, "_call", new=_call):
        with pytest.raises(AgentError):
            await ProfileExtractorAgent().run("resume text")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agents/test_profile_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.agents.profile_extractor'`

- [ ] **Step 3: Create the prompt `backend/prompts/profile_extractor.md`**

```markdown
# Profile Extractor

You extract a structured candidate profile from raw resume text.

## Resume Text
{cv_text}

## Task
Read the resume and pull out the candidate's identity, skills, work experience, and
notable projects. Use only what the resume states — do not invent skills, employers,
dates, or projects. Leave a field empty if the resume does not provide it.

- identity.name / headline / location: as written on the resume.
- core_skills.languages / frameworks / tools: split technologies into the right bucket;
  put anything that is clearly a tool or platform under tools.
- experience: one entry per role (company, role, dates, and the bullet highlights).
- featured_projects: named projects with short theme keywords.

## Output Schema — respond with valid JSON only, no preamble, no markdown fences
{"identity": {"name": "", "headline": "", "location": ""}, "core_skills": {"languages": [], "frameworks": [], "tools": []}, "experience": [{"company": "", "role": "", "dates": "", "highlights": []}], "featured_projects": [{"name": "", "themes": []}]}
```

- [ ] **Step 4: Create `backend/agents/profile_extractor.py`**

```python
from __future__ import annotations

from backend.agents.base import HAIKU, BaseAgent
from backend.schemas import ExtractedProfile


class ProfileExtractorAgent(BaseAgent):
    model = HAIKU

    async def run(self, cv_text: str) -> ExtractedProfile:
        template = self._load_prompt("profile_extractor")
        system = template.replace("{cv_text}", cv_text)
        return await self._call_structured(
            system,
            "Extract the structured profile as valid JSON using only the resume text above.",
            ExtractedProfile,
            label="profile_extractor",
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_agents/test_profile_extractor.py -v`
Expected: PASS (all tests, including Task 1's)

- [ ] **Step 6: Commit**

```bash
git add backend/agents/profile_extractor.py backend/prompts/profile_extractor.md tests/test_agents/test_profile_extractor.py
git commit -m "feat(agents): profile_extractor agent (cv_text -> ExtractedProfile)"
```

---

## Task 3: Run the extractor on CV upload (overwrite YAML, fail-open)

**Files:**
- Modify: `backend/routes/profile.py:146-183` (`upload_cv`)
- Test: `tests/test_routes/test_profile.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_routes/test_profile.py`:

```python
async def test_cv_upload_populates_yaml_from_extractor(app_client):
    from unittest.mock import AsyncMock, patch

    from backend.schemas import ExtractedProfile

    extracted = ExtractedProfile.model_validate(
        {
            "identity": {"name": "Ada Lovelace", "headline": "ML Engineer", "location": "London"},
            "core_skills": {"languages": ["Python"], "frameworks": ["FastAPI"], "tools": []},
            "experience": [],
            "featured_projects": [],
        }
    )

    with (
        patch(
            "backend.routes.profile.extract_text_from_pdf_bytes",
            new_callable=AsyncMock,
            return_value="Ada Lovelace ML Engineer with Python and FastAPI experience.",
        ),
        patch(
            "backend.routes.profile.ProfileExtractorAgent.run",
            new_callable=AsyncMock,
            return_value=extracted,
        ),
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200
    yaml_data = resp.json()["yaml_data"]
    assert "Ada Lovelace" in yaml_data
    assert "Python" in yaml_data
    assert "FastAPI" in yaml_data


async def test_cv_upload_preserves_yaml_when_extractor_fails(app_client, db_session):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, patch

    db_session.add(
        Profile(
            yaml_data="identity:\n  name: Existing Hand Edited\n",
            cv_text="old cv",
            merged_profile="old merged",
            last_refreshed_at=datetime.now(timezone.utc),
            user_id="test-user-id",
        )
    )
    await db_session.commit()

    with (
        patch(
            "backend.routes.profile.extract_text_from_pdf_bytes",
            new_callable=AsyncMock,
            return_value="New resume text with Python and SQL experience.",
        ),
        patch(
            "backend.routes.profile.ProfileExtractorAgent.run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ),
    ):
        resp = await app_client.post(
            "/api/profile/cv",
            files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    assert resp.status_code == 200  # upload must not 500 on extractor failure
    assert resp.json()["yaml_data"] == "identity:\n  name: Existing Hand Edited\n"
    assert resp.json()["cv_text"] == "New resume text with Python and SQL experience."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_routes/test_profile.py -k "populates_yaml or preserves_yaml" -v`
Expected: FAIL — `AttributeError: <module 'backend.routes.profile'> does not have the attribute 'ProfileExtractorAgent'`

- [ ] **Step 3: Wire the extractor into `upload_cv`**

In `backend/routes/profile.py`, add to the imports:

```python
import logging

from backend.agents.profile_extractor import ProfileExtractorAgent
from backend.services.profile_builder import (
    build_profile,
    build_profile_from_text,
    default_profile_yaml,
    extracted_profile_to_yaml,
    parse_profile_review_data,
)

logger = logging.getLogger(__name__)
```

(Merge `extracted_profile_to_yaml` into the existing `profile_builder` import block; add `logging`/`logger` and the agent import.)

Add this helper above `upload_cv`:

```python
async def _yaml_from_resume(cv_text: str, fallback_yaml: str) -> str:
    """Extract structured YAML from resume text. On any extractor failure, keep the
    user's existing YAML so an upload never fails because of the LLM."""
    try:
        extracted = await ProfileExtractorAgent().run(cv_text)
        return extracted_profile_to_yaml(extracted)
    except Exception:
        logger.warning("profile extraction failed; preserving existing YAML", exc_info=True)
        return fallback_yaml
```

Then in `upload_cv`, replace this block:

```python
    existing = await _latest_user_profile(db, current_user.id)
    yaml_text = existing.yaml_data if existing is not None else default_profile_yaml()
    profile = await build_profile_from_text(
```

with:

```python
    existing = await _latest_user_profile(db, current_user.id)
    fallback_yaml = existing.yaml_data if existing is not None else default_profile_yaml()
    yaml_text = await _yaml_from_resume(cv_text, fallback_yaml)
    profile = await build_profile_from_text(
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_routes/test_profile.py -v`
Expected: PASS (new tests pass; existing upload tests still pass — they don't assert `yaml_data`, and the unmocked extractor in those tests fails fast and falls back, keeping the upload 200)

- [ ] **Step 5: Commit**

```bash
git add backend/routes/profile.py tests/test_routes/test_profile.py
git commit -m "feat(profile): auto-populate yaml from resume on upload (fail-open)"
```

---

## Task 4: `PUT /profile/yaml` (editable YAML for all users)

**Files:**
- Modify: `backend/schemas.py` (add `ProfileYamlUpdate`)
- Modify: `backend/routes/profile.py` (add endpoint + `import yaml`)
- Test: `tests/test_routes/test_profile.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_routes/test_profile.py`:

```python
async def test_put_profile_yaml_persists_for_user(app_client, db_session):
    resp = await app_client.put(
        "/api/profile/yaml",
        json={"yaml_text": "identity:\n  name: Edited By User\n"},
    )
    assert resp.status_code == 200
    assert resp.json()["yaml_data"] == "identity:\n  name: Edited By User\n"
    assert "Edited By User" in resp.json()["merged_profile"]


async def test_put_profile_yaml_rejects_invalid_yaml(app_client):
    resp = await app_client.put(
        "/api/profile/yaml",
        json={"yaml_text": "identity:\n  name: [unclosed\n"},
    )
    assert resp.status_code == 422
    assert "YAML" in resp.json()["detail"]


async def test_put_profile_yaml_requires_authentication(unauthenticated_client):
    resp = await unauthenticated_client.put(
        "/api/profile/yaml", json={"yaml_text": "identity:\n  name: X\n"}
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_routes/test_profile.py -k profile_yaml -v`
Expected: FAIL — 405/404 (route not defined)

- [ ] **Step 3: Add `ProfileYamlUpdate` to `backend/schemas.py`**

Add next to `ProfileReviewUpdate`:

```python
class ProfileYamlUpdate(BaseModel):
    yaml_text: str
```

- [ ] **Step 4: Add the endpoint to `backend/routes/profile.py`**

Add `import yaml` to the imports, add `ProfileYamlUpdate` to the `backend.schemas` import line, then add this route after `update_profile_review`:

```python
@router.put("/profile/yaml", response_model=ProfileResponse)
async def update_profile_yaml(
    payload: ProfileYamlUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Save the user's own YAML profile. Available to all users."""
    try:
        yaml.safe_load(payload.yaml_text)
    except yaml.YAMLError:
        raise HTTPException(status_code=422, detail="Invalid YAML — could not parse the profile")
    existing = await _latest_user_profile(db, current_user.id)
    profile = await build_profile_from_text(
        db,
        yaml_text=payload.yaml_text,
        cv_text=existing.cv_text if existing is not None else "",
        user_id=current_user.id,
        profile_review_data=existing.profile_review_data if existing is not None else "{}",
        review_status=existing.review_status if existing is not None else "draft",
        reviewed_at=existing.reviewed_at if existing is not None else None,
    )
    await db.commit()
    await db.refresh(profile)
    return _profile_response(profile)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_routes/test_profile.py -k profile_yaml -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full backend gate**

Run: `make check`
Expected: PASS (fmt + lint + mypy + schema drift + pytest ≥70% coverage)

- [ ] **Step 7: Commit**

```bash
git add backend/schemas.py backend/routes/profile.py tests/test_routes/test_profile.py
git commit -m "feat(profile): PUT /profile/yaml editable YAML for all users"
```

---

## Task 5: Frontend API client — `saveProfileYaml`

**Files:**
- Modify: `frontend/src/api/client.ts:99-103`

- [ ] **Step 1: Add the client method**

In the `api` object, immediately after the `saveProfileReview` entry (line ~101-102), add:

```typescript
  saveProfileYaml: (yamlText: string) =>
    put<ProfileResponse>("/profile/yaml", { yaml_text: yamlText }),
```

`ProfileResponse` and the `put<T>` helper are already imported/defined in this file.

- [ ] **Step 2: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(client): saveProfileYaml API method"
```

---

## Task 6: ProfileSetup UI — editable YAML for all users, form trimmed to Links

**Files:**
- Modify: `frontend/src/pages/ProfileSetup.tsx`

This task makes YAML editable (for both the admin tools view and the regular-user view) and removes the Target-role/Skills, Projects, and Work-preferences sections, keeping only Links.

- [ ] **Step 1: Add a shared editable-YAML panel component**

Add this component above `function AdminProfileTools()` (after `ResumeUpload`):

```tsx
function YamlEditor({
  value,
  onSave,
  saving,
}: {
  value: string;
  onSave: (yaml: string) => Promise<void>;
  saving: boolean;
}) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-blue-600" />
          <h2 className="text-sm font-semibold text-slate-800">YAML Profile</h2>
        </div>
        <button
          type="button"
          onClick={() => onSave(draft)}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save YAML"}
        </button>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
        className="h-72 w-full resize-y rounded-xl border border-zinc-200 bg-zinc-50 p-4 font-mono text-xs leading-5 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
      />
      <p className="mt-2 text-xs text-zinc-400">
        Skills, experience, and projects live here. Auto-filled from your resume on upload.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Make the admin YAML editable**

In `AdminProfileTools`, add a `savingYaml` state next to the others:

```tsx
  const [savingYaml, setSavingYaml] = useState(false);
```

Add a save handler after `upload`:

```tsx
  const saveYaml = async (yaml: string) => {
    setSavingYaml(true);
    setError(null);
    try {
      setProfile(await api.saveProfileYaml(yaml));
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSavingYaml(false);
    }
  };
```

Replace the read-only YAML block (the `<div>` containing `<pre>{profile.yaml_data}</pre>`, lines ~297-305) with:

```tsx
          <YamlEditor value={profile.yaml_data} onSave={saveYaml} saving={savingYaml} />
```

- [ ] **Step 3: Trim the regular-user form to Links and add the YAML editor**

In `ProfileSetup` (the non-admin path):

a) Add YAML state + a profile load. After the existing state declarations (after `const [success, setSuccess] = useState<string | null>(null);`), add:

```tsx
  const [yamlData, setYamlData] = useState("");
  const [savingYaml, setSavingYaml] = useState(false);
```

b) In `loadReview`, after `setReview(data); setForm(data.review_data);`, also load the YAML via the profile call already present. Replace the `if (data.has_cv_text) { const profile = await api.getProfile(); setResumePreview(profile.cv_text); }` block with:

```tsx
      const profile = await api.getProfile();
      setYamlData(profile.yaml_data);
      if (data.has_cv_text) {
        setResumePreview(profile.cv_text);
      }
```

And in the catch fallback, after `setResumePreview(profile.cv_text);`, add `setYamlData(profile.yaml_data);`.

c) In `upload`, after `setResumePreview(uploadedProfile.cv_text);`, add:

```tsx
      setYamlData(uploadedProfile.yaml_data);
```

d) Add a save handler after `save`:

```tsx
  const saveYaml = async (yaml: string) => {
    setSavingYaml(true);
    setError(null);
    setSuccess(null);
    try {
      const profile = await api.saveProfileYaml(yaml);
      setYamlData(profile.yaml_data);
      setSuccess("YAML profile saved.");
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSavingYaml(false);
    }
  };
```

e) Replace `readinessItems` (lines ~448-453) with skill/project-free items:

```tsx
  const readinessItems = [
    { label: "Resume uploaded", ready: Boolean(review?.has_cv_text), detail: "Auto-fills your YAML profile" },
    { label: "YAML profile", ready: yamlData.trim().length > 0, detail: "Skills, experience, projects" },
    { label: "Links added", ready: form.links.some((link) => link.url.trim()), detail: `${form.links.length} link${form.links.length === 1 ? "" : "s"}` },
  ];
```

Also delete the now-unused `clean` helper (line ~447) and the `emptyProject` helper (lines ~29-33) and the `updateProject` function (lines ~390-398) and the `setPreferences` function (lines ~380-388) — they reference removed UI.

f) In the `<form onSubmit={save}>`, delete these three Panels entirely:
   - "Target roles and skills" Panel (lines ~524-541)
   - "Projects" Panel (lines ~543-591)
   - "Work preferences" Panel (lines ~633-665)

   Keep the "Links" Panel. Immediately before the Links Panel, insert the YAML editor (outside the grid columns, full width):

```tsx
        <div className="lg:col-span-12">
          <YamlEditor value={yamlData} onSave={saveYaml} saving={savingYaml} />
        </div>
```

   And change the Links Panel's class from `lg:col-span-5` to `lg:col-span-12` so it spans full width.

g) Remove now-unused imports from the top of the file: `FolderGit2`, `MapPin` (lucide icons used only by deleted panels), and the `ProfileReviewProject` type import if no longer referenced (keep `ProfileReviewLink`). Remove the `emptyProject` import usage. Leave `Link2`, `Sparkles`, `FileUp`, `CheckCircle2`, `RefreshCw`, `ShieldCheck`, `UserRound` — still used.

- [ ] **Step 4: Type-check and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS — no TS errors, clean vite build. Fix any "declared but never used" errors by removing the leftover symbol the compiler names.

- [ ] **Step 5: Manual smoke (optional but recommended)**

Run `make run`, log in as a regular user, upload a resume, confirm the YAML panel fills with extracted content, edit it, click Save YAML, reload, confirm it persists; confirm only the Links section remains of the structured form.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ProfileSetup.tsx
git commit -m "feat(ui): editable YAML profile for all users; form trimmed to Links"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full gate**

Run: `make check`
Expected: PASS.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Update HANDOFF.md** to mark the feature complete (current state, verification baseline), then commit.

```bash
git add HANDOFF.md
git commit -m "docs(handoff): resume -> YAML auto-populate complete"
```

---

## Out of scope (follow-ups, do NOT do here)
- Wire discovery `search_profiles` to read per-user `yaml_data` (today reads `data/candidate_profile.yaml`).
- Remove the dormant `ProfileReviewData` fields (keep `links`).
