# Cold Email Feature — Design Spec

**Date:** 2026-05-25
**Status:** Approved

---

## Goal

Extend the JobFit workflow beyond cover letter generation to include contact discovery via Hunter.io, AI-drafted cold email, a review screen, and Gmail sending. Triggered manually from the Results page — not auto-prompted after cover letter generation.

---

## Architecture

```
Results page → "Cold Email" tab
    → GET /contacts?analysis_id=...     ← resume at correct screen on mount
    → POST /contacts/discover           ← Hunter.io lookup, ranked shortlist
    → POST /contacts/{id}/draft         ← ColdEmailAgent (BaseAgent subclass)
    → POST /contacts/{id}/send          ← Gmail MCP: create_draft then send
```

All endpoints require auth (`get_current_user`). External dependencies: Hunter.io API, Gmail MCP.

---

## Data Model

### New table: `contacts` (migration step 17)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | TEXT (UUID) | No | PK |
| `analysis_id` | TEXT | No | FK → analyses |
| `email` | TEXT | No | NOT NULL — no contact stored without a verified email |
| `name` | TEXT | Yes | Nullable — Hunter.io sometimes omits |
| `title` | TEXT | Yes | Nullable — omitted in agent prompt if missing |
| `company` | TEXT | Yes | Company name from Hunter.io result |
| `source` | TEXT | No | `"hunter"` only in V1 |
| `confidence` | REAL | No | 0.0–1.0 from Hunter.io |
| `status` | TEXT | No | `"discovered"` → `"drafted"` → `"sent"` |
| `draft_subject` | TEXT | Yes | NULL until drafted |
| `draft_text` | TEXT | Yes | NULL until drafted; required before send |
| `sent_at` | TIMESTAMP | Yes | NULL until sent |
| `created_at` | TIMESTAMP | No | UTC |

**Stated design decisions:**
- `email_sent` / `email_sent_at` from the original brief collapsed into `status` + `sent_at`. Single lifecycle column is the source of truth.
- Re-drafting overwrites `draft_text` and `draft_subject` in place. No version history in V1 — any manual edits the user made in the UI are lost if they trigger re-draft.
- Contacts without a verified email are excluded before insert. A contact row without an email can never reach `sent` status, so storing one is misleading.

### Config change

Add to `backend/config.py`:
```python
hunter_api_key: str = ""
```
Same `pydantic-settings` pattern as `anthropic_api_key`. Added to `.env`.

---

## API Layer

All four endpoints live under `backend/routes/contacts.py`, registered at `/api/contacts`.

### `GET /api/contacts`

Query param: `analysis_id` (required).

Returns all contacts for the analysis sorted by `confidence DESC`, `created_at ASC`. Used by the frontend on tab mount to resume at the correct screen based on the highest-status contact.

```json
[
  {
    "id": "...", "name": "Alice Chen", "email": "alice@stripe.com",
    "title": "VP Engineering", "confidence": 0.94, "source": "hunter",
    "status": "discovered"
  }
]
```

### `POST /api/contacts/discover`

Body:
```json
{ "analysis_id": "...", "domain": null }
```

`domain` is optional. If omitted, derived heuristically from the company name extracted from the `job_parser` output: `company_name.lower().replace(" ", "") + ".com"`. Works for "Stripe" → `stripe.com`; fails for compound names.

**Flow:**
1. Load `Analysis` → extract `company` from `job_parser` `JobResult` output JSON
2. Derive or use supplied `domain`
3. Call Hunter.io `GET /domain-search?domain={domain}&limit=10`
4. Filter results with no email
5. Rank by title priority: hiring manager → engineering manager → recruiter → founder → other
6. Take up to however many results exist — no pattern-fill, no fake contacts
7. Bulk-insert all with `status='discovered'`
8. Return list

**Error cases:**
- Zero results: `200 { "contacts": [], "domain_used": "stripe.com" }` — frontend shows domain input for retry
- Hunter.io unavailable: `503 { "error": "contact_discovery_unavailable", "retry": true }` — frontend shows retry button
- Company name/domain not extractable: `422 { "error": "domain_required" }` — frontend shows domain input

### `POST /api/contacts/{contact_id}/draft`

1. Load `Contact` row + linked `Analysis` + candidate `Profile`
2. Call `ColdEmailAgent.run(profile, jd, contact_name, contact_title)`
3. If agent raises or JSON parse fails: return `500 { "error": "draft_generation_failed" }` — contact stays at `status='discovered'`, `draft_text` stays NULL
4. On success: update `draft_subject`, `draft_text`, `status='drafted'`; return `{ "subject": "...", "body": "..." }`

**State transition guarantee:** All-or-nothing. A failed draft never leaves the contact in `status='drafted'` with NULL `draft_text`. The user can retry — re-running the agent overwrites any previous partial state.

### `POST /api/contacts/{contact_id}/send`

1. Load contact row
2. If `status == 'sent'`: return `200` immediately — idempotency guard, no second Gmail call
3. If `draft_text IS NULL`: return `400 { "error": "draft_required" }` — server-side precondition
4. Call Gmail MCP: `create_draft` first, then `send` — draft lands in Gmail Drafts before firing, giving a narrow recovery window
5. Update: `status='sent'`, `sent_at=now()`
6. Return `{ "sent": true }`

**Stated design decision:** The send endpoint trusts that `draft_text` in DB reflects what the user saw and confirmed in the UI. No cryptographic confirmation token. `draft_text IS NOT NULL` is the only server-side precondition. This is a conscious V1 choice.

**Gmail failure:** `503 { "error": "gmail_unavailable", "retry": true }` — contact stays at `status='drafted'`.

---

## Services & Agent

### `backend/services/contact_discovery.py`

Single public function:
```python
async def discover_contacts(
    analysis_id: str,
    db: AsyncSession,
    domain: str | None = None,
) -> list[Contact]
```

Responsibilities: extract company name from `job_parser` output, derive or use supplied domain, call Hunter.io, filter, rank, bulk-insert. Raises `ContactDiscoveryUnavailable` (caught by route → 503) on Hunter.io HTTP errors.

Hunter.io client is an `httpx.AsyncClient` created per-call — same pattern as `github_client.py`. No retry logic in V1.

### `backend/agents/cold_email_agent.py`

```python
class ColdEmailAgent(BaseAgent):
    async def run(
        self,
        profile: str,
        jd: str,
        contact_name: str | None,
        contact_title: str | None,
    ) -> ColdEmailOutput:
        ...
```

Subclass of `BaseAgent`. Uses `prompts/cold_email.md`. Returns `ColdEmailOutput(subject: str, body: str)`.

**Prompt structure the agent targets:**
1. **Hook** — one specific thing about the company extracted from the JD (product, tech, culture signal)
2. **Who you are** — one sentence
3. **Why you're a fit** — two to three points from the job analysis
4. **Ask** — low-friction (15-minute call, not "please hire me")

**Graceful degradation:** When `contact_name` is None, prompt falls back to "Hi [Company] team". When `contact_title` is None, fit section omits title-specific framing. No hard failure on partial contact data.

**Cost monitoring:** `ColdEmailAgent` inherits `BaseAgent`, so every `_call()` automatically routes through `tracked_call()` in `instrumentation.py`. Cold email drafts appear as `coldemailagent` rows in the cost dashboard with zero extra wiring.

### `backend/schemas.py` additions

```python
class ColdEmailOutput(BaseModel):
    subject: str
    body: str

class ContactRead(BaseModel):
    id: str
    analysis_id: str
    email: str
    name: str | None
    title: str | None
    company: str | None
    source: str
    confidence: float
    status: str
    draft_subject: str | None
    draft_text: str | None
    sent_at: datetime | None
    created_at: datetime
```

---

## Frontend

### Results page

Add "Cold Email" tab alongside existing Score / Gaps / Resources / Letter / Resume tabs. Only rendered if `job_parser` output contains a non-empty `company` field.

**State persistence — DB-driven, not component state:** On tab mount, call `GET /contacts?analysis_id=...`. Derive which screen to show from the highest-status contact:
- No contacts or all `discovered` → Screen 1
- Any `drafted` → Screen 2 (pre-fill subject + body from DB)
- Any `sent` → Screen 3

Survives tab switches and page refreshes. No ephemeral flow state.

### Screen 1 — Contact Picker

Shows ranked shortlist from `POST /contacts/discover`. Each row: name, title, email, confidence badge.

**Confidence badge bucketing** (pure frontend, raw float stays in DB/API):
- `≥ 0.8` → "High" (green)
- `0.5–0.79` → "Medium" (yellow)
- `< 0.5` → "Low" (slate)

User selects one via radio button → "Draft Email" button calls `POST /contacts/{id}/draft`.

**Zero results:** Show domain input field, retry button.
**503:** Show "Hunter.io unavailable — retry" button.

### Screen 2 — Draft Review

Spinner while `POST /contacts/{id}/draft` runs (typically 5–15s for Sonnet).

Shows:
- Editable subject line (input)
- Editable body (textarea)
- "Re-draft" button
- "Send" button

**Re-draft warning — conditional:** Frontend tracks `original_draft_text` as a ref when the draft loads. On re-draft click, compare current textarea content against ref. Warning only shown if they differ: *"This will overwrite your edits."* No warning if the user hasn't typed anything.

**Send confirmation modal:**
> "Send to {email}? The email will land in Gmail Drafts briefly before sending — you can delete it from there if you act fast."

Reflect the actual `create_draft → send` flow. User clicks Confirm → `POST /contacts/{id}/send`.

### Screen 3 — Sent Confirmation

"Sent to {name} at {email}" with `sent_at` timestamp. Tab label shows ✓ indicator.

### New types (`frontend/src/types/index.ts`)

```typescript
export interface Contact {
  id: string;
  analysis_id: string;
  email: string;
  name: string | null;
  title: string | null;
  company: string | null;
  source: string;
  confidence: number;
  status: "discovered" | "drafted" | "sent";
  draft_subject: string | null;
  draft_text: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface ColdEmailDraft {
  subject: string;
  body: string;
}
```

### New API methods (`frontend/src/api/client.ts`)

```typescript
getContacts: (analysisId: string) => get<Contact[]>(`/contacts?analysis_id=${analysisId}`),
discoverContacts: (analysisId: string, domain?: string) =>
  post<Contact[]>("/contacts/discover", { analysis_id: analysisId, domain: domain ?? null }),
draftEmail: (contactId: string) =>
  post<ColdEmailDraft>(`/contacts/${contactId}/draft`, {}),
sendEmail: (contactId: string) =>
  post<{ sent: boolean }>(`/contacts/${contactId}/send`, {}),
```

No new route in `App.tsx` — the flow lives entirely inside the Results page tab.

---

## Files

| File | Action |
|---|---|
| `backend/models.py` | Add `Contact` ORM model |
| `scripts/migrate.py` | Add step 17: `contacts` table |
| `backend/config.py` | Add `hunter_api_key: str = ""` |
| `backend/services/contact_discovery.py` | Create — Hunter.io integration |
| `backend/agents/cold_email_agent.py` | Create — `ColdEmailAgent(BaseAgent)` |
| `backend/prompts/cold_email.md` | Create — prompt template |
| `backend/schemas.py` | Add `ColdEmailOutput`, `ContactRead` |
| `backend/routes/contacts.py` | Create — 4 endpoints |
| `backend/main.py` | Register contacts router |
| `frontend/src/types/index.ts` | Add `Contact`, `ColdEmailDraft` |
| `frontend/src/api/client.ts` | Add 4 API methods |
| `frontend/src/pages/Results.tsx` | Add "Cold Email" tab + 3-screen flow |

---

## Known Limitations / Future Work

| Item | Note |
|---|---|
| Pattern-fill contacts | Removed from V1 — only verified Hunter.io emails stored |
| Re-draft version history | Re-draft overwrites in place; no history in V1 |
| Web search for hook | Agent extracts hook from JD only; web search is a clean add-on if hooks feel generic |
| Email open/reply tracking | Out of scope for V1 |
| Follow-up scheduling | Out of scope for V1 |
| Bulk contact discovery | Sync endpoint per analysis; no batch mode in V1 |
| Hunter.io retry logic | No retry in V1; 503 returned to client |

---

## What This Demonstrates

| Pattern | Where |
|---|---|
| External API integration (Hunter.io) | `contact_discovery.py` — same `httpx` pattern as `github_client.py` |
| All-or-nothing state transitions | Draft endpoint — contact stays `discovered` on agent failure |
| Idempotent send endpoint | Double-click / retry safe |
| DB-driven UI state | Tab mount resumes at correct screen from DB, not component state |
| Graceful degradation | Agent handles null name/title without failing |
| Automatic cost tracking | `ColdEmailAgent` inherits `BaseAgent` — tracked_call() wired for free |
