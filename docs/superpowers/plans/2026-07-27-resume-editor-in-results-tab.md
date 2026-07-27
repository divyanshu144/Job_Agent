# Resume Editor in the Results tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Results page **Resume** tab an editable-in-place resume editor with the chat agent, by reusing the existing fork editor's logic, and drop the separate `/resume/analysis/:id` page.

**Architecture:** Extract the body of `pages/ResumeEditor.tsx` into a single reusable `components/ResumeEditorPanel.tsx` (prop `analysisId?: string` selects fork vs. master mode). The master `/resume` page and the Results Resume tab both mount that one component. The old skeleton preview, the "Edit this resume" link, and the `/resume/analysis/:analysisId` route are removed; the tailoring bullet-diffs + omitted-items are kept in a collapsed `<details>` below the editor.

**Tech Stack:** React 19 · TypeScript · Vite · Tailwind · react-router-dom · lucide-react. Frontend only.

## Global Constraints

- **Frontend only.** No backend, Pydantic schema, API, or download-rendering changes. `python scripts/check_schema_drift.py` must stay green (this change adds no schema surface).
- **No new frontend test runner** exists. Per-task verification = `cd frontend && npm run build` (tsc typecheck + vite build) + `npm run lint` (eslint). Repo-level gate = `make lint` + `make test` must stay green.
- **Behaviour-preserving extraction:** the editor logic (load, inline CAS edit, chat SSE with the `activeDocId` mid-stream guard, undo, promote, retailor, download, 409 reload, promote-confirm dialog, warnings) moves verbatim. Do not change its semantics.
- **Copy rule:** any user-facing text must avoid em/en dashes (use hyphens or rewordings).
- **Data sources stay distinct:** the panel edits the fork document from `api.getAnalysisResume(analysisId)`; the collapsed notes read `AnalysisDetail.resume_tailorer`. Do not merge them.

---

## File Structure

- **Create** `frontend/src/components/ResumeEditorPanel.tsx` — the reusable editor (controls + chat + resume preview + promote dialog + notices). Prop: `{ analysisId?: string }`. No page chrome.
- **Modify** `frontend/src/pages/ResumeEditor.tsx` — becomes a thin master-resume page: heading block + `<ResumeEditorPanel />`.
- **Modify** `frontend/src/pages/Results.tsx` — Resume tab renders `<ResumeEditorPanel analysisId={data.id} />` + collapsed `ResumeTailoringNotes`; remove `ResumeDownloadPreview`, `PreviewSection`, `downloadResume`, `downloadNotice`, and the "Edit this resume" link.
- **Modify** `frontend/src/App.tsx` — remove the `/resume/analysis/:analysisId` route.

---

### Task 1: Extract `ResumeEditorPanel`; make `/resume` (master) use it

Behaviour-preserving move. After this task the master resume editor at `/resume` looks and works exactly as before, but its guts live in the shared panel. Results is untouched in this task.

**Files:**
- Create: `frontend/src/components/ResumeEditorPanel.tsx`
- Modify: `frontend/src/pages/ResumeEditor.tsx`

**Interfaces:**
- Produces: `export function ResumeEditorPanel(props: { analysisId?: string }): JSX.Element` — a self-contained editor. When `analysisId` is a string it runs in **fork** mode (`getAnalysisResume`, Save-to-master + Re-tailor, PDF/DOCX download links); when `undefined` it runs in **master** mode (`getMasterResume`, version dropdown + New version). Renders its own load/error states, notices, and the promote-confirm dialog. Renders **no** page `<h2>` and **no** "← Results" link.

- [ ] **Step 1: Create `ResumeEditorPanel.tsx` by moving the editor body**

Copy the entire current contents of `pages/ResumeEditor.tsx` into the new file `components/ResumeEditorPanel.tsx`, then apply the edits in Steps 2-5. The import paths change because the file moves from `pages/` to `components/` — both are one level under `src/`, so the existing relative imports (`../api/client`, `../components/ResumePreview`, `../components/WarningChips`, `../components/portal`, `../types`) all still resolve unchanged. Keep them as-is.

- [ ] **Step 2: Change the entry signature from route param to prop**

Replace the top of the component:

```tsx
// REMOVE these two imports' unused parts:
// - drop `Link` and `useParams` from "react-router-dom" (no longer used here)
// - drop `FileText` from the lucide-react import (it was only in the removed header)
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Plus, RefreshCw, Send, Sparkles, Undo2 } from "lucide-react";
import { api, ApiError, errorMessage, streamResumeChat } from "../api/client";
import { ResumePreview } from "./ResumePreview";
import { WarningChips } from "./WarningChips";
import { PrimaryButton, SecondaryButton, StatusPill } from "./portal";
import type {
  ResumeDocumentResponse,
  ResumeTailorerOutput,
  ResumeVersionSummary,
  ValidationWarning,
} from "../types";
```

Note the moved-file relative paths: `./ResumePreview`, `./WarningChips`, `./portal` (same `components/` dir), and `../api/client`, `../types`.

Change the component declaration:

```tsx
export function ResumeEditorPanel({ analysisId }: { analysisId?: string }) {
  const isFork = Boolean(analysisId);
```

(Delete the old `export function ResumeEditor() {` line and the `const { analysisId } = useParams<{ analysisId?: string }>();` line — `analysisId` now comes from props.)

- [ ] **Step 3: Remove the page-header card; keep everything below it**

Delete the entire header block (the `<div className="flex flex-col justify-between gap-4 rounded-2xl border ... sm:items-center">…</div>` that contains the "Resume editor" `<h2>`, the description, the `rev` `StatusPill`, and the "← Results" `<Link>`). The panel's top-level wrapper stays `<div className="space-y-5">`, immediately followed by the `{notice && …}` block and the `<div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">` row.

- [ ] **Step 4: Re-home the `rev` pill and helper text into the controls column**

At the top of the left controls column (the `<div className="flex max-h-[calc(100vh-13rem)] flex-col gap-4 rounded-2xl border ... p-4">`), before the master/fork controls, add a compact status + helper row:

```tsx
<div className="flex items-center justify-between gap-2">
  <p className="text-xs text-[#71717a]">
    Edit inline, or tell the editor what to change. It follows your rules and flags
    anything not in your profile.
  </p>
  <StatusPill tone="neutral">rev {doc.rev}</StatusPill>
</div>
```

This preserves the `rev` indicator (previously in the deleted header) and the onboarding hint, in both modes.

- [ ] **Step 5: Verify no dangling references**

Confirm the file no longer references `useParams`, `Link`, or `FileText`, and that the component name is `ResumeEditorPanel`. Everything else (load, `applyInlineEdit`, `sendChat`, `undo`, `promote`, `retailor`, `downloadFile`, `onConflict`, the chat thread, the input, the `ResumePreview` render, and the `confirmPromote` dialog) is unchanged.

- [ ] **Step 6: Rewrite `pages/ResumeEditor.tsx` as the thin master wrapper**

Replace the entire contents of `pages/ResumeEditor.tsx` with:

```tsx
import { FileText } from "lucide-react";
import { ResumeEditorPanel } from "../components/ResumeEditorPanel";

export function ResumeEditor() {
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-[rgba(0,0,0,0.06)] bg-white p-5">
        <p className="mb-1 flex items-center gap-1.5 font-mono text-xs uppercase tracking-[0.15em] text-[#71717a]">
          <FileText className="size-3.5" />
          Master resume
        </p>
        <h2 className="text-2xl font-medium tracking-[-0.03em] text-[#0f0f17]">Resume editor</h2>
        <p className="mt-1 text-sm text-[#71717a]">
          This is your reusable base resume. Tailored copies for each role are edited from the
          Results page.
        </p>
      </div>
      <ResumeEditorPanel />
    </div>
  );
}
```

(No `analysisId` prop → master mode. The `App.tsx` `/resume` route still imports `ResumeEditor` from `./pages/ResumeEditor`, so no route change here.)

- [ ] **Step 7: Typecheck and lint**

Run: `cd frontend && npm run build`
Expected: PASS (tsc clean, vite build succeeds).

Run: `cd frontend && npm run lint`
Expected: PASS (no unused-import or undefined-name errors).

- [ ] **Step 8: Manual check — master editor unchanged**

Run the app (`make run`), open `/resume`. Expected: version dropdown + New button, chat, inline edit, undo all work exactly as before; the heading reads "Master resume / Resume editor"; the `rev` pill shows in the controls column.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ResumeEditorPanel.tsx frontend/src/pages/ResumeEditor.tsx
git commit -m "refactor(resume-editor): extract ResumeEditorPanel; master page reuses it"
```

---

### Task 2: Embed the panel in the Results Resume tab; drop the standalone fork page

**Files:**
- Modify: `frontend/src/pages/Results.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ResumeEditorPanel` from Task 1 — `<ResumeEditorPanel analysisId={data.id} />`.

- [ ] **Step 1: Import the panel and drop the now-unused `Download`/`FileEdit` usage**

In `Results.tsx`, add the import:

```tsx
import { ResumeEditorPanel } from "../components/ResumeEditorPanel";
```

Leave the existing lucide import line; `Download` and `FileEdit` may become unused after Step 3 — after that step, remove any icon names that eslint flags as unused from the `lucide-react` import in `Results.tsx`.

- [ ] **Step 2: Replace the Resume tab body**

Find the Resume tab block (currently around `pages/Results.tsx:443-462`):

```tsx
{tab === "resume" && (
  r.resume_tailorer
    ? (
      <div className="space-y-3">
        {downloadNotice && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {downloadNotice}
          </div>
        )}
        <Link
          to={`/resume/analysis/${data.id}`}
          className="inline-flex items-center gap-1.5 ..."
        >
          <FileEdit className="size-4" /> Edit this resume
        </Link>
        <ResumeDownloadPreview resume={r.resume_tailorer} onDownload={downloadResume} />
      </div>
    )
    : <EmptyPanel>Prepare documents to see tailored resume bullets.</EmptyPanel>
)}
```

Replace the entire `r.resume_tailorer ? (…)` truthy branch with:

```tsx
{tab === "resume" && (
  r.resume_tailorer
    ? (
      <div className="space-y-4">
        <ResumeEditorPanel analysisId={data.id} />
        <ResumeTailoringNotes resume={r.resume_tailorer} />
      </div>
    )
    : <EmptyPanel>Prepare documents to see tailored resume bullets.</EmptyPanel>
)}
```

- [ ] **Step 3: Delete the dead preview code and its state/handler**

In `Results.tsx`, remove:
- the `function ResumeDownloadPreview(...) { … }` definition (currently ~lines 703-814),
- the `function PreviewSection(...) { … }` definition (currently ~lines 816-832),
- the `downloadResume` handler (the `const downloadResume = async () => { … }` block, currently ~lines 200-224),
- the `downloadNotice` state: the `const [downloadNotice, setDownloadNotice] = useState<string | null>(null);` line (currently ~line 65) and any remaining `setDownloadNotice(...)` calls (all were inside `downloadResume`, now removed).

Then remove now-unused imports flagged by eslint: from `lucide-react` drop `Download` and `FileEdit` if nothing else uses them; the `Link` import from `react-router-dom` stays only if used elsewhere in the file (grep before removing).

- [ ] **Step 4: Add the `ResumeTailoringNotes` component**

Add this presentational component near the bottom of `Results.tsx` (replacing the deleted preview functions). It renders nothing when there is no metadata, else a single collapsed `<details>`:

```tsx
function ResumeTailoringNotes({ resume }: { resume: ResumeTailorerOutput }) {
  const bullets = resume.tailored_bullets ?? [];
  const omitted = resume.omitted_items ?? [];
  if (bullets.length === 0 && omitted.length === 0) return null;
  return (
    <details className="rounded-2xl border border-zinc-200 bg-white p-4 text-sm">
      <summary className="cursor-pointer font-semibold text-zinc-950">
        What the tailoring changed
      </summary>
      <div className="mt-4 space-y-4">
        {bullets.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">
              Bullet changes
            </h3>
            {bullets.map((b, i) => (
              <div key={i} className="space-y-2 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
                <p className="text-zinc-500 line-through">{b.original}</p>
                <p className="font-medium text-zinc-950">{b.rewritten}</p>
                <p className="text-xs italic text-zinc-500">{b.rationale}</p>
              </div>
            ))}
          </section>
        )}
        {omitted.length > 0 && (
          <section className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">
              Tailoring notes
            </h3>
            {omitted.map((item, i) => (
              <p key={i} className="text-amber-700">
                Omitted {item.value} because it was {item.reason}.
              </p>
            ))}
          </section>
        )}
      </div>
    </details>
  );
}
```

(`ResumeTailorerOutput` is already imported in `Results.tsx`. Field shapes `tailored_bullets[].{original,rewritten,rationale}` and `omitted_items[].{value,reason}` are the same ones the old `ResumeDownloadPreview` used, so no type risk.)

- [ ] **Step 5: Remove the fork route from `App.tsx`**

In `frontend/src/App.tsx`, delete the route:

```tsx
<Route
  path="/resume/analysis/:analysisId"
  element={<ProtectedRoute><ResumeEditor /></ProtectedRoute>}
/>
```

Keep the `/resume` route and the `import { ResumeEditor } from "./pages/ResumeEditor";` (still used by `/resume`). Leave the `location.pathname.startsWith("/resume")` breadcrumb logic and the nav link unchanged.

- [ ] **Step 6: Confirm no dangling links to the removed route**

Run: `grep -rn "/resume/analysis" frontend/src`
Expected: no matches.

- [ ] **Step 7: Typecheck and lint**

Run: `cd frontend && npm run build`
Expected: PASS.

Run: `cd frontend && npm run lint`
Expected: PASS (no unused `Download`, `FileEdit`, `downloadNotice`, `ResumeDownloadPreview`, `PreviewSection` warnings).

- [ ] **Step 8: Repo gate**

Run: `make lint`
Expected: PASS (ruff + mypy + **schema-drift** clean — no schema changed).

Run: `make test`
Expected: PASS (backend untouched; suite green).

- [ ] **Step 9: Manual check — the whole flow through the app's own UI**

Run `make run` (or the Docker image). Drive it via the app, no DB shortcuts:
1. Run an analysis to completion → open `/results/:id` → **Resume** tab.
2. Confirm the real document renders (headline/summary/skills/experience/projects/education), not skeleton bars.
3. Click a bullet → edit inline → blur → it commits (rev increments).
4. Use the chat box ("shorten the summary") → the document updates; Undo reverts it.
5. Click **Re-tailor** and **Save to master** → both succeed (promote-confirm dialog appears if warnings).
6. Download **PDF** and **DOCX** from the panel → files download.
7. Expand **"What the tailoring changed"** → bullet diffs + omitted items show.
8. Visit `/resume/analysis/<id>` directly → it no longer resolves to the editor (falls through to the app's not-found/redirect); `/resume` master editor still works.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/Results.tsx frontend/src/App.tsx
git commit -m "feat(resume-editor): edit the tailored resume in place on the Results tab

Embed ResumeEditorPanel (inline + chat) in the Resume tab; keep tailoring
bullet-diffs/omitted-items in a collapsed section; drop the standalone
/resume/analysis/:id page, its link, and the old skeleton preview."
```

---

## Self-Review

**Spec coverage:**
- Reuse via shared `ResumeEditorPanel` → Task 1. ✓
- Master `/resume` becomes thin wrapper → Task 1 Step 6. ✓
- Results tab embeds panel in place → Task 2 Step 2. ✓
- Collapsed bullet-diffs + omitted-items kept; "What changed" checklist dropped → Task 2 Step 4. ✓
- Drop `/resume/analysis/:id` route + "Edit this resume" link + `ResumeDownloadPreview`/`PreviewSection` + `downloadResume`/`downloadNotice` → Task 2 Steps 2,3,5. ✓
- No page chrome in panel; `rev` pill re-homed → Task 1 Steps 3,4. ✓
- No schema/API/backend change; drift + backend tests green → Task 2 Step 8. ✓
- Data sources stay distinct (panel = fork doc; notes = `resume_tailorer`) → Task 2 Steps 2,4. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/vague steps — every code step shows concrete JSX/commands. Line numbers are marked "currently ~" because deletions shift them; the anchor text is exact. ✓

**Type consistency:** `ResumeEditorPanel({ analysisId?: string })` is defined in Task 1 and consumed with `analysisId={data.id}` (string) in Task 2. `ResumeTailoringNotes({ resume: ResumeTailorerOutput })` uses the same `tailored_bullets`/`omitted_items` field shapes the removed `ResumeDownloadPreview` used. ✓
