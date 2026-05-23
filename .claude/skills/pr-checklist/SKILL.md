# pr-checklist — Pre-PR Checklist for JobFit Agent

Run this checklist before merging any branch. Every item must pass or have a written exception.

---

## Checklist

### Tests
- [ ] `make test` passes with exit code 0
- [ ] Coverage is at or above 70% (`--cov-fail-under=70` in pytest config)
- [ ] Any new agent has both a happy-path test and a malformed-response test
- [ ] Any new route has at least one integration test via `httpx.AsyncClient`
- [ ] If the change touches the orchestrator SSE flow, the E2E SSE sequence test still passes

### Secrets & Environment
- [ ] No API keys, tokens, or passwords in source code
- [ ] No hardcoded email addresses, usernames, or PII (these live in `candidate_profile.yaml` or `.env`)
- [ ] `.env.example` is updated if a new environment variable was added
- [ ] `.gitignore` covers any new generated or sensitive files

### API Conventions
- [ ] All new routes use `settings.api_prefix` — no hardcoded `/api`
- [ ] All route handlers have an explicit `response_model`
- [ ] All request bodies use typed Pydantic v2 schemas
- [ ] Errors returned as `HTTPException` with correct status codes (not raw 500s)
- [ ] SSE route always emits `pipeline_done` (check partial failure path too)

### Async Correctness
- [ ] No blocking I/O in async paths (no sync `requests`, no `time.sleep`, no unguarded pypdf calls)
- [ ] Any new CPU-bound work wrapped in `run_in_executor`
- [ ] `asyncio.gather` in orchestrator still uses `return_exceptions=True`

### Schema Drift
- [ ] `make lint` passes (includes Pydantic→TS drift check)
- [ ] Any new Pydantic field in `backend/schemas.py` is mirrored in `frontend/src/types/`
- [ ] `PriorOutputs` is up to date if any agent output schema changed

### Documentation
- [ ] `CLAUDE.md` updated if: a new file was added to the architecture map, a new convention was introduced, or the agent pipeline order changed
- [ ] `RESOLVER.md` updated if: a new domain skill was added
- [ ] `tasks/todo.md` items for this feature are all checked off
- [ ] `tasks/lessons.md` updated if the work surfaced any new pattern or correction

### Formatting & Lint
- [ ] `make fmt` was run (ruff format)
- [ ] `make lint` passes (ruff check + mypy strict)
- [ ] No `Any` without an inline suppression comment

---

## Exception Process

If an item cannot pass, document the exception inline in the PR description:

```
Exception: [checklist item]
Reason: ...
Follow-up: [link to issue or todo item]
```

Exceptions require explicit acknowledgement — do not silently skip items.
