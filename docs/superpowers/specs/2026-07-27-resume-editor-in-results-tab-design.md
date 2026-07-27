# Resume Editor in the Results tab — Design

**Date:** 2026-07-27
**Status:** Approved (design), pending implementation plan
**Area:** Frontend only (React / TypeScript). No backend, schema, or API changes.

---

## Problem

The Results page **Resume** tab does not show the real resume. It renders
`ResumeDownloadPreview` — an abstract mockup (grey skeleton bars, a "What changed"
checklist, before→after bullet diffs, omitted-item notes) plus a download button and an
"Edit this resume" link that navigates away to a separate editor page. To actually see or
change the tailored resume the user must leave the results context.

The dedicated editor (`pages/ResumeEditor.tsx`, fork mode) already renders the true
document with inline editing **and** a chat agent (SSE), undo, re-tailor, save-to-master,
and PDF/DOCX download. We want that experience **in place** inside the Resume tab.

## Goal

Make the Results **Resume** tab an editable-in-place editor with the chat agent — the same
experience as the fork editor — without duplicating its logic, and retain the AI-tailoring
transparency (bullet diffs + omitted items) as a secondary, collapsed detail.

Non-goals: no change to the resume data model, tailoring pipeline, download rendering, or
the master-resume editor's behaviour. No new editing capability beyond what the fork editor
already has.

---

## Approach — reuse, not rebuild

`ResumeEditor.tsx` already contains all the editing logic and handles two modes via
`isFork = Boolean(analysisId)`: **master** (`/resume`, loads `getMasterResume`, version
dropdown) and **fork** (`/resume/analysis/:analysisId`, save-to-master + re-tailor). We
extract its body into a single reusable component so there is **one** implementation of the
editing machinery, mounted in multiple places.

### New component: `components/ResumeEditorPanel.tsx`

- **Props:** `{ analysisId?: string }`. Presence of `analysisId` selects fork vs. master
  mode (replacing today's `useParams` read). Everything else is unchanged logic moved
  verbatim: load, inline CAS edit (`applyInlineEdit`), chat SSE (`sendChat` /
  `streamResumeChat` with the mid-stream `activeDocId` guard), `undo`, `promote`,
  `retailor`, `downloadFile`, 409-conflict reload, `confirmPromote` dialog, warnings.
- **No page chrome.** The panel renders only the functional editor: the controls/chat
  column, the resume-paper preview (`<ResumePreview editable onFieldChange={applyInlineEdit} />`),
  the notices, and the promote-confirm dialog. It does **not** render the page `<h2>`
  "Resume editor" heading or the "← Results" back link (that route is going away).
- The `rev {doc.rev}` `StatusPill` moves into the panel's controls row so both hosts show
  it. The short helper text ("Edit inline, or tell the editor what to change…") stays inside
  the panel, rendered compactly above the chat thread.
- Loading and error states stay inside the panel (unchanged markup).

### Hosts

1. **`pages/ResumeEditor.tsx` (master, `/resume`)** becomes a thin wrapper: its own page
   heading/description block (preserving the current master-page look) + `<ResumeEditorPanel />`
   (no `analysisId`). Reached from the nav "Resume Editor" link and the Profile dashboard —
   both **unchanged**.
2. **`pages/Results.tsx` → Resume tab** renders `<ResumeEditorPanel analysisId={data.id} />`
   in place of `ResumeDownloadPreview`, followed by a collapsed tailoring-notes section
   (below).

The Results container is `max-w-7xl` (1280px), which comfortably fits the panel's
`[380px_minmax(0,1fr)]` split — no layout compromise.

---

## Results tab — detailed changes

**Removed from `Results.tsx`:**
- The "Edit this resume" `<Link to={/resume/analysis/:id}>` (route is deleted).
- `ResumeDownloadPreview` and its `PreviewSection` helper (skeleton mockup + "What changed"
  checklist — dropped per decision).
- The tab-local `downloadResume` handler and `downloadNotice` state — download now lives in
  the panel (`downloadFile`). Verify no other tab uses `downloadNotice`; it is
  resume-specific, so it is removed with it.

**Kept, as a collapsed section beneath the panel** — new small presentational component
`ResumeTailoringNotes` (may live in `Results.tsx` or its own file), rendered only when
there is content:
- **Bullet changes** — the `resume.tailored_bullets` before→after + rationale list.
- **Tailoring notes** — the `resume.omitted_items` "Omitted X because it was Y" list.
- Wrapped in a single collapsed `<details>` ("What the tailoring changed"), default closed.
- Data source stays `r.resume_tailorer` (the original pipeline output) — unchanged. This is
  intentionally distinct from the panel's live editable fork document; the notes describe
  what the pipeline produced, the panel shows/edits the current fork.

**Gating unchanged:** the tab still only renders when `r.resume_tailorer` exists; otherwise
the existing empty state.

---

## Routing / cleanup (`App.tsx`)

- **Remove** the `/resume/analysis/:analysisId` route.
- **Keep** the `/resume` route (now the thin master wrapper), the nav link, and the
  `location.pathname.startsWith("/resume")` breadcrumb logic.
- No other file links to `/resume/analysis/...` (only Results did).

---

## Data flow

- Panel (fork mode) fetches its editable document via `api.getAnalysisResume(analysisId)` —
  the fork resume document (with `rev`, CAS writes), exactly as the standalone editor does
  today. Independent of, and unchanged from, the `AnalysisDetail.resume_tailorer` that feeds
  the collapsed notes.
- All write paths (inline patch, chat, undo, promote, retailor) keep their existing
  optimistic-update + 409-reload semantics. No SSE-contract change: chat still uses the
  `edit_start/edit_done/edit_conflict/edit_error` events via `streamResumeChat`.

## Error handling

Unchanged from the current editor: load error → error card inside the panel; write 409 →
reload + notice; chat error → assistant line; download failure → error notice. Because the
panel is embedded, these render within the tab rather than full-page.

## Testing

Frontend has no component test harness for these pages today (the drift check + `make check`
cover types/lint/backend). Verification is therefore:
- `make lint` (ruff/mypy/**schema-drift** — must stay green; this change adds no schema
  surface, so drift must remain clean) and `make test` (backend unaffected — must stay
  green).
- Manual, through the app's own flow (per project convention — no DB shortcuts): run an
  analysis → open Results → Resume tab → confirm the document renders, inline edit commits,
  the chat agent edits, undo works, re-tailor + save-to-master work, PDF/DOCX download work,
  and the collapsed tailoring notes show the bullet diffs. Confirm `/resume` (master) still
  works and `/resume/analysis/:id` now 404s / is unreachable with no dangling links.

---

## Decisions (resolved)

1. **Standalone fork page** `/resume/analysis/:analysisId` → **dropped** (route + "Edit this
   resume" link). The tab is the only home for per-analysis editing.
2. **Tailoring metadata** → **bullet diffs + omitted items kept** in a collapsed `<details>`
   below the editor; the redundant "What changed" checklist dropped.

## Out of scope

Master-editor behaviour, backend/API/schema, download rendering (`resume_latex_template.py`
et al.), and any new editing features. Pure frontend recomposition of existing pieces.
