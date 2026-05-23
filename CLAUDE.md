# JobFit Agent — Project Context

## Project Overview

<!-- TODO: Fill in once application scaffolding is complete -->
<!-- Describe: what the app does, who uses it, the core value proposition -->

**Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · SQLite | React 18 · Vite · TypeScript · Tailwind CSS · shadcn/ui | Anthropic SDK (`claude-sonnet-4-6`)

---

## Common Commands

```bash
make run          # start backend (uvicorn :8000) + frontend dev server (:5173) concurrently
make fmt          # ruff format
make lint         # ruff check + mypy + pydantic→TS schema drift check
make test         # pytest --cov --cov-fail-under=70
make docker-up    # docker-compose up --build
```

Install deps:
```bash
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

---

## Architecture Map

```
backend/
├── main.py          # FastAPI entrypoint, CORS, router includes
├── config.py        # Settings singleton (pydantic-settings); only place .env is read
├── database.py      # async engine, SessionLocal, init_db()
├── models.py        # SQLAlchemy ORM models: Profile, Analysis, JobResult
├── schemas.py       # Pydantic v2 request/response schemas + PriorOutputs
│
├── agents/
│   ├── base.py      # shared async Claude client, prompt file loader, slot injection
│   ├── job_parser.py
│   ├── match_scorer.py
│   ├── gap_analyst.py
│   ├── resource_planner.py
│   ├── cover_letter.py
│   └── resume_tailorer.py
│
├── services/
│   ├── orchestrator.py     # two-phase pipeline runner + SSE event emitter
│   ├── profile_builder.py  # merges YAML + CV text + GitHub READMEs into Profile
│   ├── github_client.py    # httpx calls to api.github.com (unauthenticated)
│   └── cv_parser.py        # pypdf text extraction
│
├── routes/
│   ├── profile.py   # GET /api/profile, POST /api/profile/refresh
│   ├── analyse.py   # POST /api/analyse (SSE stream)
│   └── history.py   # GET /api/history, GET /api/analysis/{id}
│
└── prompts/         # versioned prompt templates (.md); one per agent

frontend/src/
├── App.tsx
├── pages/
│   ├── ProfileSetup.tsx   # CV upload, GitHub list, YAML editor
│   ├── AnalyseJob.tsx     # JD paste, AgentProgress, navigates to /results/:id on done
│   └── Results.tsx        # Tabbed: Score | Gaps | Resources | Letter | Resume
├── components/
│   ├── AgentProgress.tsx  # 6 fixed-order slots; Phase 2 shows concurrent spinners
│   ├── ScoreCard.tsx
│   ├── GapList.tsx
│   ├── ResourcePanel.tsx
│   └── DocViewer.tsx      # markdown preview + copy/download
├── api/client.ts          # typed fetch wrappers + EventSource SSE dispatcher
└── types/                 # TS types mirroring backend schemas 1:1
```

<!-- TODO: Fill in any files that don't fit the map above once they exist -->

---

## Key Conventions

### Config
- Import `from backend.config import settings` — the singleton is instantiated once at module load.
- Never read `os.environ` directly anywhere outside `config.py`.

### DB Sessions
- Always inject the session as a FastAPI dependency: `db: AsyncSession = Depends(get_db)`.
- Never construct `AsyncSession` manually in a route or service.
- `init_db()` is called once in `main.py` lifespan.

### Services
- Services are plain async functions or thin classes — no global state.
- Route handlers call services; services call agents; agents call Claude. No layer skipping.

### API Prefix
- Always use `settings.api_prefix` (default `"/api"`). Never hardcode `/api` in route definitions.
- Register all routers in `main.py` with `prefix=settings.api_prefix`.

### Async
- All I/O is `async` — SQLAlchemy, httpx, Anthropic SDK.
- CPU-bound work (e.g., pypdf extraction on large files) goes in `asyncio.get_event_loop().run_in_executor(None, ...)`.
- Never call blocking functions directly in an async path.

---

## Workflow Orchestration

1. **Plan Mode Default** — enter plan mode for ANY non-trivial task (3+ steps or architectural decisions). If something goes sideways mid-implementation, STOP and re-plan rather than patching forward.

2. **Subagent Strategy** — use subagents liberally to keep the main context window clean. Offload research, codebase exploration, and parallel analysis to subagents. The main context is for decisions and writing code, not for grepping.

3. **Self-Improvement Loop** — after ANY correction, immediately update `tasks/lessons.md` with the pattern that caused the error. Review `tasks/lessons.md` at the start of every new session before touching code.

4. **Verification Before Done** — never mark a task complete without proving it works: run the relevant tests, check logs, demonstrate correctness. "It should work" is not verification.

5. **Autonomous Bug Fixing** — when given a bug report, just fix it. No permission needed. Reproduce → Locate → Fix → Verify. Use the `debug-playbook` skill.

---

## Task Management

1. Before starting any implementation, write the plan to `tasks/todo.md` as a checklist.
2. Check in with the user before beginning implementation (not during).
3. Mark items complete (`- [x]`) as you finish each one — do not batch.
4. After any correction or unexpected discovery, add an entry to `tasks/lessons.md`.

---

## Core Principles

- **Simplicity First** — make every change as small and simple as possible. Minimal code impact. If a simpler approach exists, take it.
- **No Laziness** — find root causes. No temporary fixes, no workarounds that leave debt. Hold senior developer standards.
- **Minimal Impact** — only touch files that are necessary for the task. Avoid opportunistic refactoring unless it's directly in the path of the change.
