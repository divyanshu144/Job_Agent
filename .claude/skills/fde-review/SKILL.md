# fde-review — Code Review Skill for JobFit Agent

**Trigger:** User asks to review a diff, a set of files, or a pull request.

**Output:** Structured review with severity levels. Flag only real issues — no nitpicking style when ruff handles it.

---

## Review Checklist

Run through each category. Only report findings that are actual problems.

### 1. Convention Violations (load `conventions.md` and check against it)
- [ ] Config accessed via `os.environ` directly instead of `settings`
- [ ] DB session constructed manually instead of via `Depends(get_db)`
- [ ] API prefix hardcoded as `"/api"` instead of `settings.api_prefix`
- [ ] Pydantic v1 syntax used (`class Config`, `orm_mode`)
- [ ] Agent output parsed as raw dict instead of via Pydantic schema

### 2. Async Correctness
- [ ] Blocking I/O called directly in an async function (no `await`, no `run_in_executor`)
- [ ] `time.sleep` used instead of `await asyncio.sleep`
- [ ] `asyncio.gather` used without `return_exceptions=True` in the Phase 2 pipeline
- [ ] DB session used outside its dependency scope

### 3. Error Handling at Boundaries
- [ ] Route handler lets internal exceptions escape to the client (should be `HTTPException`)
- [ ] Agent parse failure not caught and re-raised as typed `AgentError`
- [ ] SSE stream does not always emit `pipeline_done` (it must always fire, even on partial failure)
- [ ] `EventSource` on the frontend not explicitly closed on terminal events

### 4. Schema / Type Drift
- [ ] New Pydantic field added in `backend/schemas.py` but not reflected in `frontend/src/types/`
- [ ] `PriorOutputs` model missing a new agent's field
- [ ] Response model on a route decorator doesn't match what the handler returns

### 5. Security
- [ ] Secrets or API keys present in code (should be in `.env`, read via `settings`)
- [ ] User-supplied input used in a shell command or SQL string without sanitisation
- [ ] GitHub username or other PII hardcoded in source (should be in `candidate_profile.yaml`)

### 6. Agent / Prompt Quality (for changes to `backend/agents/` or `backend/prompts/`)
- [ ] Prompt does not end with the JSON schema instruction
- [ ] Cover letter or resume prompt missing the "never invent skills" grounding instruction
- [ ] Prompt slot `{prior.<agent>}` used for an agent that hasn't run yet in the pipeline order

---

## Output Format

```
## Review: <file or feature name>

### Critical (must fix before merge)
- [file:line] Description of issue and why it matters

### Major (should fix before merge)
- [file:line] Description of issue

### Minor (fix or note, low urgency)
- [file:line] Description of issue

### Approved ✓
- List of things that were checked and look correct
```

If there are no findings in a severity bucket, omit that section. If there are no findings at all, write "No issues found — LGTM."
