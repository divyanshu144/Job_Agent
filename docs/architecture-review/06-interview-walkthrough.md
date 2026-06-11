# Interview Walkthrough

## 30-Second Explanation

JobFit Agent is a full-stack AI job-application assistant. It uses FastAPI, React, Postgres, Celery, and Anthropic to analyze job descriptions against a candidate profile, stream a multi-agent pipeline live to the browser, generate tailored application materials, discover jobs, and track LLM cost and reliability.

## 2-Minute Explanation

The core design is a durable AI workflow. A user uploads a resume/profile, pastes a job description, and the backend creates an `Analysis` row. Each LLM agent writes one `JobResult`, so the system can persist partial output, retry failed steps, and rehydrate results later.

The pipeline has two phases. Phase 1 evaluates fit using `job_parser`, `match_scorer`, and `gap_analyst`. It streams progress over SSE from `POST /api/analyse`. Phase 2 generates a resource plan, cover letter, and tailored resume through `POST /api/analyse/generate/{analysis_id}`.

LLM reliability is handled through `BaseAgent`: prompts are versioned Markdown files, outputs are parsed as JSON, validated with Pydantic schemas, and corrected once if malformed. Cost and telemetry are first-class: `LLMCall` records token usage and cost; `PipelineEvent` records spans, failures, and retries.

The project also has a multi-source job discovery pipeline and a Celery-backed campaign system for regular users with target companies and cost caps.

## 5-Minute Architecture Walkthrough

Start with the UI. `frontend/src/App.tsx` defines protected routes, while `frontend/src/api/client.ts` handles REST calls and SSE parsing. For analysis, `AnalyseJob.tsx` calls `streamAnalysis()`, which posts to `/api/analyse`.

The FastAPI route in `backend/routes/analyse.py` returns a `StreamingResponse`. It does not own the pipeline logic; it formats events from `run_evaluate_pipeline()` in `backend/services/orchestrator.py`.

The orchestrator loads the user profile, computes a cache key, creates an `Analysis` row, and runs the phase-1 agents. Each agent inherits from `BaseAgent`, which loads a prompt from `backend/prompts`, calls Anthropic through `tracked_call()`, parses JSON, and validates a Pydantic model from `backend/schemas.py`.

Each successful step writes a `JobResult`. If a step fails, `to_user_error()` maps the exception to a safe error code and message. The analysis can still complete partially, and the user can retry failed steps through `/api/analysis/{analysis_id}/retry`.

Phase 2 is triggered separately. `resource_planner` runs first, then `cover_letter` and `resume_tailorer` run concurrently with separate DB sessions. When all outputs exist, `Analysis.evaluate_only` becomes false.

The database is not just storage; it is the workflow engine's state. `Analysis` is the aggregate, `JobResult` stores step outputs, `LLMCall` is the cost ledger, and `PipelineEvent` is the tracing ledger.

For background work, discovery currently uses in-process tasks in `backend/services/discovery.py`. Regular-tier campaigns use Celery tasks in `backend/tasks.py`, with fresh async DB engines created inside worker execution to avoid forked connection reuse.

## Common Interview Questions and Answers

### How do you handle LLM reliability?

LLM output is treated as untrusted external input. `BaseAgent._call_structured()` extracts JSON, validates it against a Pydantic schema, and retries once with a correction prompt if validation fails. The orchestrator isolates every agent step, persists successes, maps failures to user-safe errors, and allows targeted retry through `run_retry_pipeline()`.

### How do you control cost?

The system controls cost structurally and operationally. Structurally, it splits evaluation from generation so users do not pay for documents unless they want them. It uses cheaper Haiku models for parsing/scoring and richer Sonnet models for generation. Discovery has an Anthropic Batch API path for cheaper non-urgent relevance checks. Operationally, every model call writes an `LLMCall` row with tokens and cost, and campaigns enforce user cost caps through `backend/services/usage.py`.

### How do you make this production-ready?

The first fixes are auth hardening, durable discovery execution, database-enforced result uniqueness, and global cost caps. Specifically: require a strong production JWT secret, set secure cookies and CSRF protection, move discovery from in-process tasks to Celery, add a unique constraint for `(analysis_id, agent_name)`, and apply budget checks to all user-attributed LLM calls.

### What was the hardest technical decision?

The hardest decision was modeling LLM work as a durable step workflow instead of one opaque request. It adds complexity: an `Analysis` aggregate, `JobResult` rows, retries, partial flags, SSE events, and finalization logic. But it enables the product features that matter: live progress, partial recovery, retries, history, cost tracking, and reuse from background workflows.

### What would you improve next?

I would move discovery to Celery, because it is the clearest production reliability gap. The campaign system already has the right worker pattern in `backend/tasks.py`; discovery should use the same durable queue model instead of `asyncio.create_task()` inside the API process.

### How is this different from a simple ChatGPT wrapper?

A wrapper sends one prompt and renders one answer. This system has typed agents, persistent workflow state, partial-result recovery, targeted retries, SSE streaming, cost accounting, tracing, background discovery, campaign automation, authentication, and database-backed history. The architecture is built around making LLM work reliable enough to support a real user workflow.

## Strong Resume Bullets

- Designed a six-agent Anthropic pipeline with durable `Analysis`/`JobResult` workflow state, SSE progress streaming, partial failure handling, and targeted retries.
- Implemented LLM observability with `LLMCall` cost ledger and `PipelineEvent` trace ledger for token usage, latency, failures, retries, and per-run cost dashboards.
- Built multi-source job discovery with deduplication, keyword prefiltering, Haiku relevance screening, Batch API support, and scored job feeds.
- Added typed Pydantic contracts and validators around LLM outputs to reduce invalid JSON, inconsistent scores, and unsupported resume claims.
- Implemented Celery-backed campaign execution with per-user target companies, monthly cost caps, daily run caps, and fork-safe async DB session handling.
