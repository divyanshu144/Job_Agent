# Resume Editor — Plan 5: Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The tsenta-style resume editor UI — a split-pane page (chat left, live locked-format preview right) serving both entry points (standalone `/resume` master + per-analysis fork at `/resume/analysis/:analysisId`), with inline direct editing, POST-SSE chat, warning chips, versions, undo/restore, rules, save-to-master (confirm flow), re-tailor (decision I-1a), and downloads — plus the small backend prep the UI needs (warnings-on-read, response-schema fields, the re-tailor endpoint, and the Plan-4 final-review follow-ups).

**Architecture:** One `ResumeEditor` page component parameterized by entry point (master vs fork), following house conventions exactly: `portal.tsx` primitives (`PageShell`/`Panel`/`PrimaryButton`/`SecondaryButton`), function components + local `useState`/`useEffect`, `api.*` client one-liners over the private `get/post/patch/del` helpers, and a new `streamResumeChat` that reuses the existing fetch+ReadableStream SSE parse loop with the resume-chat event vocabulary (`edit_start/edit_done/edit_conflict/edit_error` — the existing `_streamSSE` switch is hardcoded to pipeline events). The locked ATS preview is a read-oriented render of `ResumeTailorerOutput` with click-to-edit fields (blur → CAS `PATCH`; 409 → refetch + notice). TS types mirror backend schemas 1:1 and are added to the schema-drift `PAIRS`.

**Tech Stack:** React 19 · react-router-dom v7 (classic API) · TypeScript · Tailwind (house palette `#0f0f17`/`#5b5bd6`, raw-hex arbitrary values) · lucide-react · existing cookie-auth fetch client. Backend prep: FastAPI/pytest as prior plans.

## Global Constraints

- **Frontend verification gate** (no test runner exists in `frontend/` and adding one is OUT of scope): `cd frontend && npm run build` (tsc + vite) and `npm run lint` must pass, plus `make check` (which includes `scripts/check_schema_drift.py`). Component tests are explicitly not required by this plan; backend changes get pytest as usual.
- **Types discipline:** every new backend response schema consumed by the UI gets a same-named interface in `frontend/src/types/index.ts` AND a `PAIRS` entry in `scripts/check_schema_drift.py` (field-name parity is regex-checked; one field per line).
- **SSE:** do NOT touch `_streamSSE`'s pipeline switch (frozen contract). Add a parallel `streamResumeChat` with its own switch. The chat endpoint is POST — the existing fetch+reader approach handles that; `EventSource` does not.
- **CAS everywhere:** every write sends `base_rev` from the last-known `rev`; on 409 the UI refetches, shows a short notice ("Resume changed elsewhere — reloaded latest"), and re-applies nothing automatically. The PATCH 409 detail is `{message, rev, content}`; the promote 409 detail is `{message, warnings}`; the chat conflict arrives as an `edit_conflict` SSE event `{rev, content}` — three shapes, code against each where it occurs.
- **Warning chips:** keyed off `rule` for copy; dedupe client-side on `(rule, detail)`; dismissible per-render (client state only); never render `detail` verbatim for `style_dash` (per Plan 3 final review).
- Backend conventions unchanged (settings/prefix/Depends(get_db)/services layering); `make check` green after every task that touches Python.
- House style: named-export function components, `portal.tsx` primitives, inline Tailwind, `lucide-react` icons, plain `useEffect` + `api.*` fetching, no new deps, no state library.

---

### Task 1: Backend prep — warnings-on-read, schema fields, re-tailor endpoint, Plan-4 follow-ups

**Files:**
- Modify: `backend/schemas.py` (`ResumeDocumentResponse` + `RetailorRequest`), `backend/routes/resume.py`, `backend/routes/history.py`, `backend/services/orchestrator.py` (blank-master guard), `backend/services/resume_document.py` (annotation), `docs/superpowers/specs/2026-07-22-resume-editor-design.md` (§9 asymmetry paragraph)
- Create: `backend/services/resume_retailor.py`
- Test: `tests/test_routes/test_resume_analysis.py` (append), `tests/test_routes/test_resume_chat.py` (append), `tests/test_orchestrator/test_master_as_base.py` (append), `tests/test_services/test_resume_retailor.py`

**Interfaces (what the frontend tasks rely on):**
- `ResumeDocumentResponse` gains `analysis_id: str | None = None`, `created_at: datetime`, `warnings: list[ValidationWarning] = Field(default_factory=list)` — warnings populated (recomputed, never persisted) by `GET /resume` and `GET /analysis/{id}/resume`; empty elsewhere.
- `POST /analysis/{analysis_id}/resume/retailor` with `RetailorRequest(base_rev: int)` → re-runs the tailorer against the CURRENT master+profile+stored priors and applies the result to the fork via `apply_write(source="tailor")` (CAS: stale → the standard 409-with-current-state). Returns `ResumeDocumentResponse`.
- Plan-4 follow-ups: M-4 blank-master guard in the degradation hook; M-1 shared `_resolve_resume_output` helper in `history.py` + PDF-variant test; M-2 fork-chat route test; M-3 loop-closure test (promote → next tailoring context); M-7 `ensure_analysis_resume` return annotation `-> ResumeDocument`; REC-1 grounding-asymmetry paragraph appended to design §9.

- [ ] **Step 1: Schema changes (+ failing schema-level assertions later via routes)**

In `backend/schemas.py`: add to `ResumeDocumentResponse` (after `rev`):

```python
    analysis_id: str | None = None
    created_at: datetime
    warnings: list[ValidationWarning] = Field(default_factory=list)
```

and append:

```python
class RetailorRequest(BaseModel):
    base_rev: int = Field(ge=0)
```

In `backend/routes/resume.py`'s `_to_response`, pass the new fields (`analysis_id=doc.analysis_id`, `created_at=doc.created_at`) and add an optional `warnings` parameter:

```python
def _to_response(
    doc: ResumeDocument, warnings: list[ValidationWarning] | None = None
) -> ResumeDocumentResponse:
    return ResumeDocumentResponse(
        id=doc.id,
        kind=doc.kind,
        name=doc.name,
        is_active=doc.is_active,
        rev=doc.rev,
        analysis_id=doc.analysis_id,
        created_at=doc.created_at,
        content=ResumeTailorerOutput.model_validate(json.loads(doc.content_json or "{}")),
        updated_at=doc.updated_at,
        warnings=warnings or [],
    )
```

- [ ] **Step 2: Warnings-on-read (I-2) — failing tests first**

Append to `tests/test_routes/test_resume_analysis.py`:

```python
async def test_get_analysis_resume_recomputes_warnings(app_client, db_session):
    await make_profile(db_session, user_id=_USER_ID, profile_review_data="{}",
                       yaml_data="plain profile", merged_profile="m")
    analysis, doc = await _fork(db_session, headline="Raised revenue 300% at Globex")
    resp = await app_client.get(f"/api/analysis/{analysis.id}/resume")
    assert resp.status_code == 200
    rules = [w["rule"] for w in resp.json()["warnings"]]
    assert "unsupported_metric" in rules  # recomputed on read, never persisted
```

Implement: in `get_analysis_resume` and `get_active_resume` (`routes/resume.py`), recompute before responding:

```python
    profile = await get_owned_profile(db, current_user.id)
    source = build_resume_tailoring_context(profile) if profile is not None else ""
    content = ResumeTailorerOutput.model_validate(json.loads(doc.content_json or "{}"))
    return _to_response(doc, warnings=validate_resume_faithfulness(content, source))
```

(`get_active_resume` already fetches the profile for seeding — reuse it; do not double-fetch.)

- [ ] **Step 3: Re-tailor service + endpoint (decision I-1a) — failing tests first**

```python
# tests/test_services/test_resume_retailor.py
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import backend.models  # noqa: F401
from backend.models import JobResult
from backend.schemas import ResumeTailorerOutput
from backend.services import resume_document as docsvc
from backend.services.resume_retailor import retailor_analysis
from tests.factories import make_analysis, make_profile, make_user


async def test_retailor_applies_via_cas_and_preserves_history(db_session):
    user = await make_user(db_session)
    profile = await make_profile(db_session, user_id=user.id, profile_review_data="{}",
                                 yaml_data="Python", merged_profile="m")
    analysis = await make_analysis(db_session, user_id=user.id)
    db_session.add(JobResult(analysis_id=analysis.id, agent_name="job_parser",
                             output_json=json.dumps({"required_skills": ["Python"],
                                                     "nice_to_have": [], "role_type": "BE",
                                                     "seniority": "Senior"})))
    await db_session.flush()
    fork = await docsvc.ensure_analysis_resume(
        db_session, user.id, analysis.id, json.dumps({"headline": "old tailoring"})
    )
    new_output = ResumeTailorerOutput(headline="re-tailored from new master")
    with patch(
        "backend.agents.resume_tailorer.ResumeTailorerAgent.run",
        new_callable=AsyncMock, return_value=new_output,
    ):
        doc = await retailor_analysis(db_session, user.id, analysis, fork, base_rev=0)
    assert doc.rev == 1  # applied as a CAS write — old tailoring is one undo away
    assert json.loads(doc.content_json)["headline"] == "re-tailored from new master"
```

```python
# backend/services/resume_retailor.py
"""Re-tailor an analysis's fork against the CURRENT master/profile (decision I-1a).

Applied through apply_write(source="tailor"), so a re-tailor is an ordinary CAS write:
concurrency-safe, revision-snapshotted, and one undo away from the prior content. The
JobResult row is untouched — it remains the historical pipeline record.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.resume_tailorer import ResumeTailorerAgent
from backend.models import Analysis, JobResult, Profile, ResumeDocument
from backend.schemas import PriorOutputs
from backend.services import resume_document as docsvc
from backend.services.orchestrator import _profile_context
from backend.services.profile_builder import get_owned_profile


async def _priors_for(db: AsyncSession, analysis_id: str) -> PriorOutputs:
    rows = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    data = {
        r.agent_name: json.loads(r.output_json)
        for r in rows
        if r.output_json and r.agent_name in ("job_parser", "match_scorer", "gap_analyst")
    }
    return PriorOutputs.model_validate(data)


async def retailor_analysis(
    db: AsyncSession,
    user_id: str,
    analysis: Analysis,
    fork: ResumeDocument,
    base_rev: int,
) -> ResumeDocument:
    profile: Profile | None = await get_owned_profile(db, user_id)
    prior = await _priors_for(db, analysis.id)
    profile_ctx = await _profile_context(db, profile, "resume_tailorer", analysis.jd_text, prior)
    agent = ResumeTailorerAgent().with_tracking(db, analysis_id=analysis.id, user_id=user_id)
    output = await agent.run(profile_ctx, analysis.jd_text, prior)
    return await docsvc.apply_write(
        db, fork, output, base_rev=base_rev, source="tailor",
        summary="Re-tailored from current master",
    )
```

Route (in `backend/routes/resume.py`; import `RetailorRequest`, `retailor_analysis`, and `Analysis`):

```python
@router.post("/analysis/{analysis_id}/resume/retailor", response_model=ResumeDocumentResponse)
async def retailor(
    analysis_id: str,
    data: RetailorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResumeDocumentResponse:
    analysis = (
        await db.execute(
            select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    doc = await svc.get_analysis_resume(db, current_user.id, analysis_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="No tailored resume for this analysis")
    try:
        doc = await retailor_analysis(db, current_user.id, analysis, doc, base_rev=data.base_rev)
    except StaleRevError as exc:
        current = exc.current
        raise HTTPException(
            status_code=409,
            detail={"message": "Resume changed; reload and retry", "rev": current.rev,
                    "content": json.loads(current.content_json or "{}")},
        ) from exc
    return _to_response(doc)
```

Route test (append to `tests/test_routes/test_resume_analysis.py`): happy path (mock `ResumeTailorerAgent.run` as in the service test, POST `{"base_rev": 0}` → 200, rev 1, new headline) + 401 (add `("POST", "/api/analysis/x/resume/retailor")` to the auth loop with a `{"base_rev": 0}` body).

- [ ] **Step 4: Plan-4 follow-ups (M-1, M-2, M-3, M-4, M-7, REC-1)**

- **M-4:** in the two orchestrator failure-branch hooks, extend the guard to `if master is not None and master.content_json not in (None, "", "{}")` (both parallel and sequential sites).
- **M-1:** in `history.py`, extract the duplicated fork-preference block into `async def _resolve_resume_output(db, user_id, analysis_id, result) -> ResumeTailorerOutput` (raises 404 when neither source exists); use it in both download routes; append a PDF-variant test mirroring the DOCX one but asserting the PDF route returns 200 with `application/pdf` after a fork edit (content-parity of PDF bytes is not asserted — pdflatex output isn't greppable; the 200 + content-type + fork-preference code path via the shared helper is the point). If `pdflatex` is unavailable in the test env, the existing history tests show how PDF rendering is handled/mocked — mirror that (check `tests/test_routes/test_history.py` for the established pattern before writing).
- **M-2:** append to `tests/test_routes/test_resume_chat.py` a fork-chat test: create a fork (reuse `_fork`-style setup from `test_resume_analysis.py` — import or duplicate the helper), monkeypatch `resume_chat.apply_chat_edit` to return a canned `ResumeChatResult`, POST `/api/resume/{fork.id}/chat`, assert `edit_done` arrives (proves `_owned_doc` chat on forks at the route layer).
- **M-3:** append to `tests/test_orchestrator/test_master_as_base.py` a loop-closure test: seed master, create fork with distinctive content, `promote_analysis_to_master`, then assert `await _profile_context(session, profile, "resume_tailorer", "jd", PriorOutputs())` contains the promoted headline.
- **M-7:** change `ensure_analysis_resume`'s return annotation to `-> ResumeDocument` (it never returns None); adjust any now-unneeded narrowing at call sites.
- **REC-1:** append to design spec §9 (before §9.5):

```markdown
**Grounding-corpus asymmetry (recorded from Plan 4 review).** The pipeline's
`validate_resume_tailorer` grounds against profile+master (it MUTATES output — omitting
supported master content would destroy the user's curation), while the chat editor and the
save-to-master guard ground against the profile ONLY (flag-only paths; the user is ground
truth). Consequences: (a) a chat-fabricated claim the user confirmed into the master is
treated as grounded by the pipeline validator, but re-flags at EVERY promotion attempt —
silent accretion is impossible; (b) legitimate master-curated content not literally in the
profile re-warns on every promotion — UI copy must read "not found in your profile, verify",
never "fabricated".
```

- [ ] **Step 5: Full gate + commit**

Run: `make check` → green (all new tests + 702 existing).

```bash
git add backend/ docs/superpowers/specs/2026-07-22-resume-editor-design.md tests/
git commit -m "feat(resume-editor): warnings-on-read, retailor endpoint, response fields, Plan-4 follow-ups"
```

---

### Task 2: TS types, schema-drift pairs, API client + chat SSE helper

**Files:**
- Modify: `frontend/src/types/index.ts`, `scripts/check_schema_drift.py`, `frontend/src/api/client.ts`

**Interfaces (what Tasks 3–5 import):**
- Types: `ResumeDocumentResponse`, `ResumeVersionSummary`, `ResumeRevisionSummary`, `EditRuleResponse`, `ResumeChatResult` (reusing existing `ResumeTailorerOutput`, `ValidationWarning`).
- `api` additions: `getMasterResume()`, `listResumeVersions()`, `createResumeVersion(name, cloneActive)`, `patchResumeVersion(id, body)`, `deleteResumeVersion(id)`, `patchResumeContent(id, baseRev, content)`, `undoResume(id, baseRev)`, `restoreResume(id, baseRev, targetRev)`, `listResumeRevisions(id)`, `listEditRules()`, `deleteEditRule(id)`, `getAnalysisResume(analysisId)`, `saveToMaster(analysisId, name, confirm)`, `retailorAnalysis(analysisId, baseRev)`.
- `streamResumeChat(docId, baseRev, instruction, callbacks): () => void` with `ResumeChatCallbacks { onEditStart?; onEditDone?(r: ResumeChatResult); onEditConflict?(c: {rev: number; content: ResumeTailorerOutput}); onEditError?(message: string); onStreamEnd?(); }`.

- [ ] **Step 1: Types**

Append to `frontend/src/types/index.ts` (mirror field names EXACTLY — the drift check is regex field-name parity, one field per line):

```ts
export interface ResumeVersionSummary {
  id: string;
  name: string;
  is_active: boolean;
  rev: number;
  updated_at: string;
}

export interface ResumeRevisionSummary {
  rev: number;
  source: string;
  summary?: string | null;
  created_at: string;
}

export interface EditRuleResponse {
  id: string;
  mode: string;
  text: string;
  scope: string;
}

export interface ResumeDocumentResponse {
  id: string;
  kind: string;
  name: string;
  is_active: boolean;
  rev: number;
  analysis_id?: string | null;
  created_at: string;
  content: ResumeTailorerOutput;
  updated_at: string;
  warnings: ValidationWarning[];
}

export interface ResumeChatResult {
  rev: number;
  content: ResumeTailorerOutput;
  summary: string;
  warnings: ValidationWarning[];
  new_rule?: EditRuleResponse | null;
  fallback_used: boolean;
}
```

(If `ValidationWarning` is missing from the TS file — the explorer says it exists — reuse it; do NOT redefine.)

- [ ] **Step 2: Schema-drift pairs**

Append to `PAIRS` in `scripts/check_schema_drift.py`:

```python
    ("ResumeDocumentResponse", "ResumeDocumentResponse"),
    ("ResumeVersionSummary", "ResumeVersionSummary"),
    ("ResumeRevisionSummary", "ResumeRevisionSummary"),
    ("ResumeChatResult", "ResumeChatResult"),
    ("EditRuleResponse", "EditRuleResponse"),
```

Run `python scripts/check_schema_drift.py` — must pass (fix any field-name mismatch by correcting the TS side).

- [ ] **Step 3: API client additions**

In `frontend/src/api/client.ts`, add to the `api` object (reusing the private `get/post/patch/del` helpers — read their exact names first; the explorer reports `get/patch/put/del` plus direct fetch for binary):

```ts
  // --- resume editor ---
  getMasterResume: () => get<ResumeDocumentResponse>("/resume"),
  listResumeVersions: () => get<ResumeVersionSummary[]>("/resume/versions"),
  createResumeVersion: (name: string, clone_active = true) =>
    post<ResumeDocumentResponse>("/resume/versions", { name, clone_active }),
  patchResumeVersion: (id: string, body: { name?: string; make_active?: boolean }) =>
    patch<ResumeDocumentResponse>(`/resume/versions/${id}`, body),
  deleteResumeVersion: (id: string) => del(`/resume/versions/${id}`),
  patchResumeContent: (id: string, base_rev: number, content: ResumeTailorerOutput) =>
    patch<ResumeDocumentResponse>(`/resume/${id}/content`, { base_rev, content }),
  undoResume: (id: string, base_rev: number) =>
    post<ResumeDocumentResponse>(`/resume/${id}/undo?base_rev=${base_rev}`, {}),
  restoreResume: (id: string, base_rev: number, target_rev: number) =>
    post<ResumeDocumentResponse>(`/resume/${id}/restore?base_rev=${base_rev}&target_rev=${target_rev}`, {}),
  listResumeRevisions: (id: string) => get<ResumeRevisionSummary[]>(`/resume/${id}/revisions`),
  listEditRules: () => get<EditRuleResponse[]>("/resume/rules"),
  deleteEditRule: (id: string) => del(`/resume/rules/${id}`),
  getAnalysisResume: (analysisId: string) =>
    get<ResumeDocumentResponse>(`/analysis/${analysisId}/resume`),
  saveToMaster: (analysisId: string, name: string | null, confirm: boolean) =>
    post<ResumeDocumentResponse>(`/analysis/${analysisId}/resume/save-to-master`, { name, confirm }),
  retailorAnalysis: (analysisId: string, base_rev: number) =>
    post<ResumeDocumentResponse>(`/analysis/${analysisId}/resume/retailor`, { base_rev }),
```

Adapt `post`/`del` names/signatures to what actually exists in the file (if `post` doesn't exist as a helper, mirror `patch`'s shape). Import the new types at the top. NOTE: `undoResume`/`restoreResume` pass `base_rev`/`target_rev` as QUERY params (the backend routes declare them as query params) — keep the querystring form.

- [ ] **Step 4: `streamResumeChat`**

Add beside `_streamSSE` (do NOT modify `_streamSSE`), reusing its exact fetch/reader/decode/split logic with a resume-event switch:

```ts
export interface ResumeChatCallbacks {
  onEditStart?: () => void;
  onEditDone?: (result: ResumeChatResult) => void;
  onEditConflict?: (c: { rev: number; content: ResumeTailorerOutput }) => void;
  onEditError?: (message: string) => void;
  onStreamEnd?: () => void;
}

export function streamResumeChat(
  docId: string,
  baseRev: number,
  instruction: string,
  cb: ResumeChatCallbacks,
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const resp = await fetch(`${BASE}/resume/${docId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_rev: baseRev, instruction }),
        credentials: "include",
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        cb.onEditError?.(`Chat request failed (${resp.status})`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          let event = "";
          let data = "";
          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice(7);
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!event) continue;
          const payload = data ? JSON.parse(data) : {};
          switch (event) {
            case "edit_start":
              cb.onEditStart?.();
              break;
            case "edit_done":
              cb.onEditDone?.(payload as ResumeChatResult);
              break;
            case "edit_conflict":
              cb.onEditConflict?.(payload as { rev: number; content: ResumeTailorerOutput });
              break;
            case "edit_error":
              cb.onEditError?.((payload as { message?: string }).message ?? "Edit failed");
              break;
          }
        }
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        cb.onEditError?.(String(e));
      }
    } finally {
      cb.onStreamEnd?.();
    }
  })();
  return () => controller.abort();
}
```

(Match the surrounding file's style for the parse loop — if `_streamSSE`'s internals differ meaningfully from the above, mirror ITS proven loop and keep only the switch/callback shape new.)

- [ ] **Step 5: Verify + commit**

Run: `cd frontend && npm run build && npm run lint` → clean; `python scripts/check_schema_drift.py` → pass.

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts scripts/check_schema_drift.py
git commit -m "feat(resume-editor): TS types, drift pairs, api client + chat SSE helper"
```

---

### Task 3: `ResumePreview` — locked ATS render with inline editing + warning chips

**Files:**
- Create: `frontend/src/components/ResumePreview.tsx`, `frontend/src/components/WarningChips.tsx`

**Interfaces:**
- `<ResumePreview content={ResumeTailorerOutput} editable onFieldChange={(mutator) => void} />` — renders the locked single-column ATS layout (headline · summary · SKILLS · EXPERIENCE · PROJECTS · EDUCATION, mirroring `resume_docx.py`'s section order). When `editable`, clicking a text region swaps in an input/textarea; blur or Enter commits via `onFieldChange(mutator)` where `mutator(draft)` applies the change to a deep copy — the PARENT owns save/CAS (Task 4).
- `<WarningChips warnings={ValidationWarning[]} />` — deduped on `(rule, detail)`, dismissible (local state), copy keyed off `rule` (a `RULE_COPY` map; `style_dash` renders fixed copy, never its `detail`).

- [ ] **Step 1: `WarningChips.tsx`**

```tsx
import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { ValidationWarning } from "../types";

const RULE_COPY: Record<string, string> = {
  unsupported_employer: "Employer not found in your profile",
  unsupported_institution: "Institution not found in your profile",
  unsupported_skill: "Skill not found in your profile",
  unsupported_metric: "Number not found in your profile",
  style_dash: "Contains an em/en dash, rephrase or use commas",
};

export function WarningChips({ warnings }: { warnings: ValidationWarning[] }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const seen = new Set<string>();
  const unique = warnings.filter((w) => {
    const key = `${w.rule}|${w.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return !dismissed.has(key);
  });
  if (unique.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {unique.map((w) => {
        const key = `${w.rule}|${w.detail}`;
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300"
            title={w.rule === "style_dash" ? RULE_COPY.style_dash : w.detail}
          >
            <AlertTriangle className="size-3" />
            {RULE_COPY[w.rule] ?? w.detail}
            <button
              type="button"
              aria-label="Dismiss warning"
              onClick={() => setDismissed(new Set(dismissed).add(key))}
              className="ml-0.5 text-amber-300/60 hover:text-amber-200"
            >
              <X className="size-3" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: `ResumePreview.tsx`**

One inline-editable primitive + the locked layout. Complete component:

```tsx
import { useEffect, useRef, useState } from "react";
import type { ResumeTailorerOutput } from "../types";

type Mutator = (draft: ResumeTailorerOutput) => void;

function EditableText({
  value,
  placeholder,
  multiline = false,
  editable,
  className = "",
  onCommit,
}: {
  value: string;
  placeholder: string;
  multiline?: boolean;
  editable: boolean;
  className?: string;
  onCommit: (next: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);
  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };
  if (!editable || !editing) {
    return (
      <span
        className={`${className} ${editable ? "cursor-text rounded px-0.5 hover:bg-[#5b5bd6]/10" : ""} ${value ? "" : "text-neutral-500 italic"}`}
        onClick={() => editable && setEditing(true)}
      >
        {value || placeholder}
      </span>
    );
  }
  const shared = {
    value: draft,
    onBlur: commit,
    className: `${className} w-full rounded border border-[#5b5bd6]/50 bg-[#0f0f17] px-1 outline-none`,
  };
  return multiline ? (
    <textarea
      {...shared}
      ref={(el) => (ref.current = el)}
      rows={Math.max(2, Math.ceil(draft.length / 80))}
      onChange={(e) => setDraft(e.target.value)}
    />
  ) : (
    <input
      {...shared}
      ref={(el) => (ref.current = el)}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && commit()}
    />
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="border-b border-neutral-700 pb-1 text-xs font-bold uppercase tracking-widest text-neutral-300">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function ResumePreview({
  content,
  editable = false,
  onFieldChange,
}: {
  content: ResumeTailorerOutput;
  editable?: boolean;
  onFieldChange?: (mutate: Mutator) => void;
}) {
  const change = (mutate: Mutator) => onFieldChange?.(mutate);
  return (
    <article className="mx-auto max-w-[52rem] space-y-6 rounded-lg bg-white/[0.03] p-8 font-serif text-sm leading-relaxed text-neutral-100">
      <header className="space-y-1 text-center">
        <EditableText
          value={content.headline}
          placeholder="Headline"
          editable={editable}
          className="text-xl font-bold"
          onCommit={(v) => change((d) => void (d.headline = v))}
        />
        <div>
          <EditableText
            value={content.summary}
            placeholder="Professional summary"
            multiline
            editable={editable}
            className="block text-left text-sm text-neutral-300"
            onCommit={(v) => change((d) => void (d.summary = v))}
          />
        </div>
      </header>

      {(content.skills.length > 0 || editable) && (
        <Section title="Skills">
          <p>{content.skills.join(" · ")}</p>
        </Section>
      )}

      {(content.experience.length > 0 || editable) && (
        <Section title="Work Experience">
          {content.experience.map((exp, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-baseline justify-between gap-4">
                <span className="font-semibold">
                  {[exp.company, exp.role].filter(Boolean).join(" | ")}
                </span>
                <span className="shrink-0 text-xs text-neutral-400">{exp.dates}</span>
              </div>
              <ul className="list-disc space-y-0.5 pl-5">
                {exp.bullets.map((b, j) => (
                  <li key={j}>
                    <EditableText
                      value={b}
                      placeholder="Bullet"
                      multiline
                      editable={editable}
                      onCommit={(v) =>
                        change((d) => void (d.experience[i].bullets[j] = v))
                      }
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {(content.projects.length > 0 || editable) && (
        <Section title="Projects">
          {content.projects.map((proj, i) => (
            <div key={i} className="space-y-1">
              <span className="font-semibold">{proj.name}</span>
              {proj.description && <p className="text-neutral-300">{proj.description}</p>}
              <ul className="list-disc space-y-0.5 pl-5">
                {proj.bullets.map((b, j) => (
                  <li key={j}>
                    <EditableText
                      value={b}
                      placeholder="Bullet"
                      multiline
                      editable={editable}
                      onCommit={(v) => change((d) => void (d.projects[i].bullets[j] = v))}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {(content.education.length > 0 || editable) && (
        <Section title="Education">
          {content.education.map((edu, i) => (
            <div key={i} className="flex items-baseline justify-between gap-4">
              <span>
                <span className="font-semibold">{edu.institution}</span>
                {edu.degree ? `, ${edu.degree}` : ""}
              </span>
              <span className="shrink-0 text-xs text-neutral-400">{edu.dates}</span>
            </div>
          ))}
        </Section>
      )}
    </article>
  );
}
```

Skills/company/role/dates/institution stay read-only-in-preview for v1 (bulk edits go through chat or future affordances) — headline, summary, and bullets are the inline-editable hot paths. This is a deliberate v1 scope line; note it in the commit message.

- [ ] **Step 3: Verify + commit**

Run: `cd frontend && npm run build && npm run lint` → clean.

```bash
git add frontend/src/components/ResumePreview.tsx frontend/src/components/WarningChips.tsx
git commit -m "feat(resume-editor): locked ATS preview with inline editing + warning chips (v1: headline/summary/bullets editable inline)"
```

---

### Task 4: `ResumeEditor` page — split-pane, chat, versions, undo, CAS

**Files:**
- Create: `frontend/src/pages/ResumeEditor.tsx`
- Modify: `frontend/src/App.tsx` (routes + nav + pageTitles)

**Interfaces:**
- Routes: `/resume` (master mode) and `/resume/analysis/:analysisId` (fork mode) → same `<ResumeEditor />`, mode from `useParams`.
- Master mode: version selector (list/create/switch/rename/delete), downloads hidden (master has no analysis-scoped download).
- Fork mode: "Save to master" (409 → confirm dialog listing warnings), "Re-tailor from current master", Download PDF/DOCX (existing api helpers), link back to `/results/:analysisId`.
- Both: chat pane (streamResumeChat; summary lines; `fallback_used` note "applied with a backup model"; rule-captured toast; conflict → reload), inline edit → `patchResumeContent` (409 → reload + notice), Undo button (`undoResume`), revision count via `listResumeRevisions`, `WarningChips` fed by doc.warnings ∪ latest chat warnings.

- [ ] **Step 1: The page component**

```tsx
// frontend/src/pages/ResumeEditor.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download, History, RefreshCw, Send, Undo2 } from "lucide-react";
import { api, streamResumeChat, ApiError } from "../api/client";
import { ResumePreview } from "../components/ResumePreview";
import { WarningChips } from "../components/WarningChips";
import type {
  ResumeDocumentResponse,
  ResumeTailorerOutput,
  ResumeVersionSummary,
  ValidationWarning,
} from "../types";

type ChatLine = { role: "user" | "assistant"; text: string };

export function ResumeEditor() {
  const { analysisId } = useParams<{ analysisId?: string }>();
  const isFork = Boolean(analysisId);

  const [doc, setDoc] = useState<ResumeDocumentResponse | null>(null);
  const [versions, setVersions] = useState<ResumeVersionSummary[]>([]);
  const [chatLog, setChatLog] = useState<ChatLine[]>([]);
  const [chatWarnings, setChatWarnings] = useState<ValidationWarning[]>([]);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmPromote, setConfirmPromote] = useState<ValidationWarning[] | null>(null);
  const cancelStream = useRef<(() => void) | null>(null);

  const load = useCallback(async () => {
    try {
      const d = isFork
        ? await api.getAnalysisResume(analysisId!)
        : await api.getMasterResume();
      setDoc(d);
      setError(null);
      if (!isFork) setVersions(await api.listResumeVersions());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [analysisId, isFork]);

  useEffect(() => {
    void load();
    return () => cancelStream.current?.();
  }, [load]);

  const onConflict = useCallback(
    (rev: number, content: ResumeTailorerOutput) => {
      setDoc((d) => (d ? { ...d, rev, content } : d));
      setNotice("Resume changed elsewhere — reloaded the latest version.");
    },
    [],
  );

  const applyInlineEdit = async (mutate: (draft: ResumeTailorerOutput) => void) => {
    if (!doc) return;
    const draft: ResumeTailorerOutput = JSON.parse(JSON.stringify(doc.content));
    mutate(draft);
    try {
      const updated = await api.patchResumeContent(doc.id, doc.rev, draft);
      setDoc(updated);
      setNotice(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        await load();
        setNotice("Resume changed elsewhere — reloaded; your last edit was not applied.");
      } else {
        setError(String(e));
      }
    }
  };

  const sendChat = () => {
    if (!doc || !instruction.trim() || busy) return;
    const text = instruction.trim();
    setInstruction("");
    setBusy(true);
    setChatLog((l) => [...l, { role: "user", text }]);
    cancelStream.current = streamResumeChat(doc.id, doc.rev, text, {
      onEditDone: (r) => {
        setDoc((d) =>
          d ? { ...d, rev: r.rev, content: r.content } : d,
        );
        setChatWarnings(r.warnings);
        const suffix = r.fallback_used ? " (applied with a backup model)" : "";
        const rule = r.new_rule ? ` · Rule saved: ${r.new_rule.mode} ${r.new_rule.text}` : "";
        setChatLog((l) => [...l, { role: "assistant", text: `${r.summary}${suffix}${rule}` }]);
      },
      onEditConflict: (c) => onConflict(c.rev, c.content),
      onEditError: (m) => setChatLog((l) => [...l, { role: "assistant", text: m }]),
      onStreamEnd: () => setBusy(false),
    });
  };

  const undo = async () => {
    if (!doc) return;
    try {
      setDoc(await api.undoResume(doc.id, doc.rev));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await load();
      else setError(String(e));
    }
  };

  const promote = async (confirm: boolean) => {
    if (!analysisId) return;
    try {
      await api.saveToMaster(analysisId, null, confirm);
      setConfirmPromote(null);
      setNotice("Saved to your master resume.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // detail: {message, warnings}
        const detail = (e as ApiError & { detail?: { warnings?: ValidationWarning[] } }).detail;
        setConfirmPromote(detail?.warnings ?? []);
      } else {
        setError(String(e));
      }
    }
  };

  const retailor = async () => {
    if (!doc || !analysisId) return;
    setBusy(true);
    try {
      setDoc(await api.retailorAnalysis(analysisId, doc.rev));
      setNotice("Re-tailored from your current master (undo available).");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) await load();
      else setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <p className="p-8 text-sm text-red-400">{error}</p>;
  if (!doc) return <p className="p-8 text-sm text-neutral-400">Loading resume…</p>;

  const allWarnings = [...doc.warnings, ...chatWarnings];

  return (
    <div className="flex h-full gap-6 p-6">
      {/* Left: chat + controls */}
      <div className="flex w-96 shrink-0 flex-col gap-4">
        {!isFork && (
          <div className="flex items-center gap-2 text-sm">
            <select
              value={doc.id}
              onChange={async (e) => {
                await api.patchResumeVersion(e.target.value, { make_active: true });
                await load();
              }}
              className="flex-1 rounded border border-neutral-700 bg-[#0f0f17] px-2 py-1.5"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                  {v.is_active ? " (active)" : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="rounded border border-neutral-700 px-2 py-1.5 text-neutral-300 hover:border-[#5b5bd6]"
              onClick={async () => {
                const name = window.prompt("Version name", "New version");
                if (name) {
                  await api.createResumeVersion(name, true);
                  await load();
                }
              }}
            >
              + New
            </button>
          </div>
        )}

        {isFork && (
          <div className="flex flex-wrap gap-2 text-sm">
            <button type="button" onClick={() => void promote(false)}
              className="rounded bg-[#5b5bd6] px-3 py-1.5 font-medium text-white hover:bg-[#6b6be0]">
              Save to master
            </button>
            <button type="button" onClick={() => void retailor()} disabled={busy}
              className="inline-flex items-center gap-1.5 rounded border border-neutral-700 px-3 py-1.5 text-neutral-300 hover:border-[#5b5bd6] disabled:opacity-50">
              <RefreshCw className="size-3.5" /> Re-tailor
            </button>
            <Link to={`/results/${analysisId}`}
              className="rounded border border-neutral-700 px-3 py-1.5 text-neutral-300 hover:border-[#5b5bd6]">
              ← Results
            </Link>
          </div>
        )}

        <WarningChips warnings={allWarnings} />
        {notice && <p className="text-xs text-amber-300">{notice}</p>}

        <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-neutral-800 p-3 text-sm">
          {chatLog.length === 0 && (
            <p className="text-neutral-500">
              Tell me what to change, or set a rule with “always” / “never” and I’ll follow it
              on every future edit.
            </p>
          )}
          {chatLog.map((line, i) => (
            <p key={i} className={line.role === "user" ? "text-neutral-100" : "text-[#9b9bf0]"}>
              {line.text}
            </p>
          ))}
          {busy && <p className="animate-pulse text-neutral-500">Editing…</p>}
        </div>

        <div className="flex items-end gap-2">
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendChat();
              }
            }}
            rows={2}
            placeholder="Tell the editor what to change…"
            className="flex-1 resize-none rounded border border-neutral-700 bg-[#0f0f17] px-3 py-2 text-sm outline-none focus:border-[#5b5bd6]"
          />
          <button type="button" onClick={sendChat} disabled={busy || !instruction.trim()}
            aria-label="Send"
            className="rounded bg-[#5b5bd6] p-2 text-white disabled:opacity-40">
            <Send className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-3 text-xs text-neutral-400">
          <button type="button" onClick={() => void undo()}
            className="inline-flex items-center gap-1 hover:text-neutral-200">
            <Undo2 className="size-3.5" /> Undo
          </button>
          <span className="inline-flex items-center gap-1">
            <History className="size-3.5" /> rev {doc.rev}
          </span>
          {isFork && (
            <>
              <button type="button" className="inline-flex items-center gap-1 hover:text-neutral-200"
                onClick={() => window.open(`/api/analysis/${analysisId}/resume.pdf`, "_blank")}>
                <Download className="size-3.5" /> PDF
              </button>
              <button type="button" className="inline-flex items-center gap-1 hover:text-neutral-200"
                onClick={() => window.open(`/api/analysis/${analysisId}/resume.docx`, "_blank")}>
                <Download className="size-3.5" /> DOCX
              </button>
            </>
          )}
        </div>
      </div>

      {/* Right: live preview */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <ResumePreview content={doc.content} editable onFieldChange={applyInlineEdit} />
      </div>

      {/* Promote-confirm dialog */}
      {confirmPromote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md space-y-4 rounded-lg border border-neutral-700 bg-[#16161f] p-6">
            <h3 className="font-semibold">Unverified claims</h3>
            <p className="text-sm text-neutral-300">
              Some content wasn’t found in your profile. Verify it’s accurate before saving to
              your master resume.
            </p>
            <WarningChips warnings={confirmPromote} />
            <div className="flex justify-end gap-2 text-sm">
              <button type="button" onClick={() => setConfirmPromote(null)}
                className="rounded border border-neutral-700 px-3 py-1.5 text-neutral-300">
                Cancel
              </button>
              <button type="button" onClick={() => void promote(true)}
                className="rounded bg-[#5b5bd6] px-3 py-1.5 font-medium text-white">
                Save anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Two adaptation notes for the implementer:** (1) `ApiError` — check whether `client.ts`'s `_errorMessage` preserves the parsed `detail` object on the error (the promote-409 path needs `detail.warnings`; the explorer says errors throw `ApiError { status }` with a message string). If `detail` isn't preserved, extend `ApiError` with an optional `detail?: unknown` field set from the parsed body — a small, backward-compatible client change; do it in `client.ts`, don't hack around it in the page. (2) `window.open` for downloads relies on cookie auth on same-origin `/api` — this matches how the browser would fetch; if `Results.tsx`'s blob-anchor pattern is preferred for consistency, use `api.downloadResumePdf`-style helpers instead — follow whichever `Results.tsx` does.

- [ ] **Step 2: Routes + nav in `App.tsx`**

- `import { ResumeEditor } from "./pages/ResumeEditor";`
- Routes (non-admin section): `<Route path="/resume" element={<ProtectedRoute><ResumeEditor /></ProtectedRoute>} />` and `<Route path="/resume/analysis/:analysisId" element={<ProtectedRoute><ResumeEditor /></ProtectedRoute>} />`
- `pageTitles`: `"/resume": "Resume Editor"` (the param route falls back to whatever the map's default behavior is — check how `pageTitles` handles `/results/:id` and mirror it).
- Nav: a `<NavLink to="/resume" ...>` with `FileText` (add to the existing `lucide-react` import), in the main section — mirror the existing NavLink structure/classNames exactly.

- [ ] **Step 3: Verify + commit**

Run: `cd frontend && npm run build && npm run lint` → clean.

```bash
git add frontend/src/pages/ResumeEditor.tsx frontend/src/App.tsx
git commit -m "feat(resume-editor): split-pane editor page (chat SSE, versions, undo, promote, re-tailor)"
```

---

### Task 5: Results-page integration + end-to-end smoke

**Files:**
- Modify: `frontend/src/pages/Results.tsx` (Resume tab: add "Edit this resume" affordance)
- Verify: whole stack

**Interfaces:**
- The Results Resume tab gains a `PrimaryButton`-styled link "Edit this resume" → `/resume/analysis/{data.id}` above the existing `ResumeDownloadPreview` (which stays — it's the "what changed" summary; the editor is the editing surface). If `api.getAnalysisResume` 404s (legacy analysis with no fork), the button is hidden — probe with a small effect, or simpler: always render the link and let the editor page show its error state with a "Re-run generation" hint; choose the simpler-consistent option and note it.

- [ ] **Step 1: Results.tsx change**

In the Resume tab's render block (near `ResumeDownloadPreview`), add:

```tsx
<Link
  to={`/resume/analysis/${data.id}`}
  className="inline-flex items-center gap-2 rounded bg-[#5b5bd6] px-4 py-2 text-sm font-medium text-white hover:bg-[#6b6be0]"
>
  <FileEdit className="size-4" /> Edit this resume
</Link>
```

(`Link` from react-router-dom and `FileEdit` from lucide-react — add to existing imports; match the tab's surrounding layout/spacing.)

- [ ] **Step 2: Full verification**

- `make check` → green (backend untouched since Task 1, but the drift check re-runs).
- `cd frontend && npm run build && npm run lint` → clean.
- **Live smoke (the run skill's standard for this repo):** with Docker Postgres/Redis up, run backend on a free port + `cd frontend && npm run dev`; then via the app only (no DB writes): register/login → `/resume` seeds and renders → inline-edit headline (rev bumps) → chat edit (event stream renders summary; warnings chips if any) → undo → create/switch a version → run an analysis → open `/resume/analysis/:id` → re-tailor → save-to-master (confirm dialog on flagged content) → download. Capture any breakage as fix commits.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Results.tsx
git commit -m "feat(resume-editor): Results page links to the per-analysis editor"
```

---

## Self-Review

**Spec coverage (design §11 frontend + §6 preview + I-1a + Plan-4 pre-reqs):**
- Split-pane, chat-left/preview-right; Resume nav item; both entry points, one component → Task 4 ✓
- Locked ATS format, no template/font knobs; inline direct edit → PATCH+CAS with 409 handling → Tasks 3–4 ✓ (v1 inline scope: headline/summary/bullets — stated explicitly; other fields via chat)
- Chat with summaries, always/never rule capture toast, `fallback_used` note, conflict reload → Task 4 ✓
- Warning chips: dedupe, dismissible, copy keyed off `rule`, `style_dash` never renders detail → Task 3 ✓ (per Plan 3 review)
- Versions UI (create/switch; rename/delete available via API — rename/delete UI deferred to keep v1 lean, `patchResumeVersion`/`deleteResumeVersion` are wired in the client for it) — deviation noted ✓
- Undo + rev indicator; revisions endpoint wired in client (full history browser deferred) ✓
- Save-to-master confirm flow (409 warnings dialog) → Task 4 ✓ ; Re-tailor (I-1a) → Tasks 1+4 ✓
- Downloads (fork PDF/DOCX) → Task 4; Results integration → Task 5 ✓
- Warnings-on-read (I-2), response fields (M-5), degradation guard (M-4), download helper+PDF test (M-1), fork-chat test (M-2), loop-closure test (M-3), annotation (M-7), §9 asymmetry paragraph (REC-1) → Task 1 ✓
- §6 contract test (HTML/DOCX/PDF parity): NOT automatable without a frontend test runner (explicitly out of scope) — the live smoke in Task 5 is the parity check for v1; recorded as a deviation for the final review to weigh.
- TS mirrors + drift PAIRS → Task 2 ✓

**Placeholder scan:** clean — the two "adaptation notes" (ApiError.detail, download pattern) direct the implementer to a concrete decision procedure, not a TBD.

**Type consistency:** `streamResumeChat(docId, baseRev, instruction, cb)` matches Task 4's call; `api.*` signatures match usage (`patchResumeContent(id, rev, content)`, `saveToMaster(analysisId, null, confirm)`, `retailorAnalysis(analysisId, doc.rev)`); `ResumeDocumentResponse.warnings` produced in Task 1 `_to_response`, consumed in Task 4 `allWarnings`; `RetailorRequest(base_rev)` matches the client body `{ base_rev }`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-resume-editor-05-frontend.md`. Five tasks; Task 1 is backend (pytest-gated), Tasks 2–5 are frontend (build+lint+drift-gated, live smoke in Task 5). Plan 6 (cover-letter mode) remains.
