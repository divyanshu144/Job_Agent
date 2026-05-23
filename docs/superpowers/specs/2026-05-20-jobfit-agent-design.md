# JobFit Agent — Design Spec
**Date:** 2026-05-20
**Status:** Approved

---

## 1. Goal

Build a production-grade local-first web application that analyses a job description against a candidate profile (CV + GitHub projects + skills YAML) and produces:

1. A match score (0–100) with profile gaps
2. Skill gap analysis with curated learning resources
3. A tailored cover letter
4. A tailored resume (bullet-point rewrites)

Runnable with `make run`, deployable later to AWS.

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, uvicorn |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui |
| AI | Anthropic SDK (`anthropic`), model `claude-sonnet-4-6` |
| CV parsing | `pypdf` |
| GitHub | REST API (`api.github.com`), unauthenticated |
| Storage | SQLite via SQLAlchemy 2.0 (async) |
| Config | `data/candidate_profile.yaml` + `.env` for secrets |
| Containerisation | Dockerfile + docker-compose.yml |
| Quality | `ruff` (lint + format), `mypy` (strict), `pytest` |

---

## 3. Architecture

```
┌────────────────────────────────────────────────┐
│  Frontend (React 18 + Vite + TS + Tailwind)    │
│  ProfileSetup | AnalyseJob | Results (tabs)     │
└──────────────────┬─────────────────────────────┘
                   │ HTTP + SSE
┌──────────────────▼─────────────────────────────┐
│  Backend (FastAPI + uvicorn, port 8000)         │
│  routes/ → services/ → agents/                 │
│  SQLAlchemy async → SQLite (data/jobfit.db)     │
└──────────────────┬─────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   Anthropic API         GitHub REST API
   (claude-sonnet-4-6)   (api.github.com, unauthed)
```

**Key decisions:**
- All backend I/O is `async`: SQLAlchemy 2.0 async sessions, `httpx` for GitHub, async Anthropic client.
- Candidate profile is built once at startup and cached in SQLite; refreshed on demand via `POST /api/profile/refresh`.
- The 6-agent pipeline runs in `orchestrator.py`, which owns the SSE event loop and streams per-agent progress.
- No auth layer — local-first personal tool; secrets live in `.env`.
- Docker: single-stage build copies Vite `dist/` into backend static mount; `uvicorn` serves everything on port 8000 in production.

---

## 4. Project Structure

```
jobfit-agent/
├── CLAUDE.md
├── .env.example
├── Makefile
├── docker-compose.yml
├── Dockerfile
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── job_parser.py
│   │   ├── match_scorer.py
│   │   ├── gap_analyst.py
│   │   ├── resource_planner.py
│   │   ├── cover_letter.py
│   │   └── resume_tailorer.py
│   │
│   ├── services/
│   │   ├── profile_builder.py
│   │   ├── github_client.py
│   │   ├── cv_parser.py
│   │   └── orchestrator.py
│   │
│   ├── routes/
│   │   ├── profile.py
│   │   ├── analyse.py
│   │   └── history.py
│   │
│   └── prompts/
│       ├── job_parser.md
│       ├── match_scorer.md
│       ├── gap_analyst.md
│       ├── resource_planner.md
│       ├── cover_letter.md
│       └── resume_tailorer.md
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── ProfileSetup.tsx
│   │   │   ├── AnalyseJob.tsx
│   │   │   └── Results.tsx
│   │   ├── components/
│   │   │   ├── ScoreCard.tsx
│   │   │   ├── GapList.tsx
│   │   │   ├── ResourcePanel.tsx
│   │   │   ├── DocViewer.tsx
│   │   │   └── AgentProgress.tsx
│   │   ├── api/client.ts
│   │   └── types/
│   ├── tailwind.config.ts
│   ├── vite.config.ts
│   └── package.json
│
├── data/
│   ├── candidate_profile.yaml
│   ├── cv.pdf                  ← gitignored
│   └── jobfit.db               ← gitignored
│
└── tests/
    ├── test_agents/
    ├── test_services/
    └── test_routes/
```

---

## 5. Candidate Profile Schema

File: `data/candidate_profile.yaml`

```yaml
identity:
  name: Divyanshu Charak
  github_username: divyanshu144
  target_roles: [ML Engineer, Data Scientist, AI/Automation Developer]
  location_preferences: [UK, Remote, Europe]

core_skills:
  languages: [Python, TypeScript, SQL, R]
  ml: [scikit-learn, XGBoost, SHAP, PyTorch]
  llm: [Claude API, OpenAI, RAG, prompt engineering, LangChain]
  web: [FastAPI, React, Next.js, Redux]
  data: [PostgreSQL, SQLite, Redis, pandas, NumPy]
  cloud: [AWS (ECS, RDS, S3), Docker, GitHub Actions]

domains:
  - Energy policy analytics
  - Document intelligence (RAG)
  - LLM evaluation & MLOps

featured_projects:
  - repo: divyanshu144/docchat
  - repo: divyanshu144/promptops
  - repo: divyanshu144/epc-south-west

currently_learning:
  - AWS deployment (ECS Fargate)
  - Agentic pipelines
```

---

## 6. Agent Pipeline & Data Flow

### Agent Signatures

Each agent: `async def run(profile: Profile, jd: str, prior: PriorOutputs) -> <TypedOutput>`

`PriorOutputs` is a typed Pydantic model holding all upstream agent results. Accessing prior outputs uses dotted paths: `prior.job_parser`, `prior.match_scorer`, etc.

### Dependency Graph

| Agent | Reads from `prior` |
|---|---|
| `job_parser` | — |
| `match_scorer` | `prior.job_parser` |
| `gap_analyst` | `prior.match_scorer` |
| `resource_planner` | `prior.gap_analyst` |
| `cover_letter` | `prior.match_scorer`, `prior.gap_analyst` |
| `resume_tailorer` | `prior.match_scorer`, `prior.gap_analyst` |

### Orchestrator — Two-Phase Execution

The orchestrator runs in two phases to minimise wall-clock time:

```python
# Phase 1 — sequential; each depends on the previous
parsed    = await job_parser.run(profile, jd)
scored    = await match_scorer.run(profile, jd, parsed)
gaps      = await gap_analyst.run(profile, jd, scored)
resources = await resource_planner.run(profile, jd, gaps)

# Phase 2 — parallel; both depend only on Phase 1 outputs
phase1_prior = PriorOutputs(
    job_parser=parsed, match_scorer=scored,
    gap_analyst=gaps, resource_planner=resources,
)
cover_letter, resume = await asyncio.gather(
    cover_letter_agent.run(profile, jd, phase1_prior),
    resume_tailorer.run(profile, jd, phase1_prior),
    return_exceptions=True,
)
```

`return_exceptions=True` ensures a failure in one Phase 2 agent does not cancel the other. Failures are handled per-agent in the assembly phase.

### SSE Event Contract

`/api/analyse` streams Server-Sent Events. The frontend renders agents by fixed ID order, not arrival order.

```
event: pipeline_start    data: {"total_agents": 6}
event: agent_start       data: {"agent": "job_parser"}
event: agent_done        data: {"agent": "job_parser", "output": {...}}
event: agent_start       data: {"agent": "match_scorer"}
event: agent_done        data: {"agent": "match_scorer", "output": {...}}
event: agent_start       data: {"agent": "gap_analyst"}
event: agent_done        data: {"agent": "gap_analyst", "output": {...}}
event: agent_start       data: {"agent": "resource_planner"}
event: agent_done        data: {"agent": "resource_planner", "output": {...}}
event: agent_start       data: {"agent": "cover_letter"}
event: agent_start       data: {"agent": "resume_tailorer"}
event: agent_done        data: {"agent": "resume_tailorer", "output": {...}}
event: agent_done        data: {"agent": "cover_letter", "output": {...}}
event: pipeline_error    data: {"agent": "...", "error": "..."}   ← per-agent, non-terminal
event: pipeline_done     data: {"analysis_id": "uuid", "score": 82, "partial": false}
```

`pipeline_done` always fires. `partial: true` when one or more agents failed.

### Prompt Design

- **System prompt**: role definition + merged candidate profile as context.
- **User prompt**: JD text + prior agent outputs as structured JSON.
- **Slots**: `{profile}`, `{jd}`, `{prior.<agent>}` — injected by `base.py`.
- Every prompt ends with an explicit JSON schema and: `"Respond with valid JSON only — no preamble, no markdown fences."`
- Resume and cover letter prompts include: `"Ground everything in the candidate's actual experience — never invent skills or projects."`

---

## 7. Pydantic Schemas

```python
# backend/schemas.py

class JobParserOutput(BaseModel):
    required_skills: list[str]
    nice_to_have: list[str]
    years_experience: int | None
    role_type: str
    seniority: str

class MatchScorerOutput(BaseModel):
    score: int  # 0–100
    matched_skills: list[str]
    missing_skills: list[str]
    partial_matches: list[str]

class GapAnalystOutput(BaseModel):
    critical_gaps: list[GapItem]
    nice_to_have_gaps: list[GapItem]

class ResourcePlannerOutput(BaseModel):
    gaps: list[ResourceItem]  # skill, courses[], books[], projects[], estimated_hours

class CoverLetterOutput(BaseModel):
    subject: str
    body: str
    tone_notes: str

class ResumeTailorerOutput(BaseModel):
    tailored_bullets: list[BulletItem]  # original, rewritten, rationale

class PriorOutputs(BaseModel):
    job_parser: JobParserOutput | None = None
    match_scorer: MatchScorerOutput | None = None
    gap_analyst: GapAnalystOutput | None = None
    resource_planner: ResourcePlannerOutput | None = None
    cover_letter: CoverLetterOutput | None = None
    resume_tailorer: ResumeTailorerOutput | None = None
```

---

## 8. API Endpoints

```
GET    /api/profile              → returns merged profile (YAML + CV + GitHub)
POST   /api/profile/refresh      → re-fetches GitHub READMEs, re-parses CV; updates last_refreshed_at
POST   /api/analyse              → body: { jd: str }; streams SSE pipeline progress
GET    /api/history              → paginated past analyses (?limit=20&offset=0)
GET    /api/analysis/{id}        → single analysis with all 6 agent outputs
```

### SQLAlchemy Models

- **Profile**: `id`, `yaml_data`, `cv_text`, `github_data`, `merged_profile`, `last_refreshed_at`
- **Analysis**: `id`, `jd_text`, `profile_id`, `created_at`, `partial` (bool)
- **JobResult**: `id`, `analysis_id`, `agent_name`, `output_json`, `error` (nullable)

---

## 9. Frontend Design

### Routes

| Route | Page | Purpose |
|---|---|---|
| `/` | `ProfileSetup` | CV upload, GitHub repo list, YAML editor with live validation |
| `/analyse` | `AnalyseJob` | JD paste area, triggers pipeline, shows `AgentProgress` |
| `/results/:id` | `Results` | Tabbed: Score · Gaps · Resources · Letter · Resume |
| `/history` | History | Past analyses list, click to reload any result |

On `pipeline_done`, `AnalyseJob` navigates to `/results/:id`. The Results page handles both fresh and reloaded analyses identically.

### Components

- **`AgentProgress`**: 6 fixed-order agent slots (pending → spinning → done). Phase 2 agents show two concurrent spinners; rendered by agent ID, not arrival order.
- **`ScoreCard`**: circular progress dial (0–100), matched vs missing skill chips.
- **`GapList`**: critical gaps in red, nice-to-have in amber, each expandable.
- **`ResourcePanel`**: per-gap accordion — courses / books / projects with estimated hours.
- **`DocViewer`**: markdown-rendered cover letter and resume bullets, copy-to-clipboard + download as `.txt`.

### SSE Client (`api/client.ts`)

- Uses native `EventSource` with `{ withCredentials: false }`.
- Typed dispatcher maps event names to callbacks.
- Explicitly closes (`eventSource.close()`) and disables auto-reconnect on `pipeline_done` or `pipeline_error`.

### State

- `useState` + React Context for active analysis. No external state library.
- TypeScript types in `src/types/` mirror backend Pydantic schemas 1:1 (manually synced; no codegen).

---

## 10. Testing

### Coverage target: 70% (`--cov-fail-under=70`)

| Suite | Tests |
|---|---|
| `test_agents/` | 2 per agent: happy-path + malformed Claude response (truncated JSON, extra prose, type mismatches). Total: 12. |
| `test_services/` | `profile_builder` merge logic; `cv_parser` text extraction; `github_client` README fetch (mocked `httpx`). Total: 3+. |
| `test_routes/` | `GET /api/profile`, `POST /api/analyse`, `GET /api/history` via `httpx.AsyncClient` against ASGI app with mocked orchestrator. Total: 3+. |
| `test_orchestrator/` | One E2E test with a stub Claude client asserting the full SSE event sequence (all 6 `agent_start` + `agent_done` events + `pipeline_done`). |

Minimum baseline: **19 tests**.

---

## 11. Tooling

### Makefile Targets

```
make run        → uvicorn backend + vite dev server (concurrently)
make test       → pytest --cov --cov-fail-under=70
make fmt        → ruff format
make lint       → ruff check + mypy (strict) + pydantic→TS schema drift check
make docker-up  → docker-compose up --build
```

### Quality Gates

- `ruff`: rule sets `E`, `F`, `I`
- `mypy`: strict mode, `--ignore-missing-imports` where stubs unavailable
- No `Any` unless explicitly suppressed with a comment
- Pydantic→TS drift check runs as part of `make lint`: a script compares field names and types in `backend/schemas.py` against `frontend/src/types/` and fails if they diverge
- Alembic deferred — add only when first schema migration is needed

---

## 12. CLAUDE.md Content (to be committed at project root)

Key convention to record:

> The orchestrator runs in two phases. Phase 1 is strictly sequential: Job Parser → Match Scorer → Gap Analyst → Resource Planner. Phase 2 runs Cover Letter and Resume Tailorer concurrently via `asyncio.gather(..., return_exceptions=True)`, because they share Phase 1 inputs but don't depend on each other. SSE events are emitted per agent start and finish, not per phase, so the frontend renders concurrent agents as independent spinners.

---

## 13. Build Order

1. Directory structure + `CLAUDE.md`
2. Backend: `config.py` → `database.py` → `models.py` → `schemas.py` → `services/` → `agents/` → `routes/` → `main.py`
3. Prompt templates (`backend/prompts/*.md`)
4. Frontend: `types/` → `api/client.ts` → `components/` → `pages/` → `App.tsx`
5. `Makefile`, `Dockerfile`, `docker-compose.yml`
6. Tests
7. `make fmt && make lint && make test` — fix until clean
