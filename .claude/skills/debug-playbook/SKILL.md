# debug-playbook — Debugging Skill for JobFit Agent

**Trigger:** User reports a bug, error, exception, test failure, or unexpected behaviour.

**Hard rule:** Follow the five steps in order. Do not jump to Fix before Isolate. Do not mark fixed before Verify.

---

## Step 1 — Reproduce

Confirm you can trigger the failure deterministically.

- Identify the exact input (JD text, profile state, agent name, API call) that causes the issue
- Check if the failure is consistent or intermittent
- Note the environment: local `make run`, Docker, or test suite

If you cannot reproduce it, say so explicitly and ask for more context. Do not guess.

---

## Step 2 — Locate

Find where in the codebase the failure originates.

For backend errors:
- Read the full traceback top-to-bottom. The root cause is usually NOT the last line.
- Use `semantic_search_nodes` or `query_graph` to find the relevant function before grepping.
- Check: is this in the agent, the orchestrator, a service, or a route?

For SSE/streaming issues:
- Check whether `pipeline_done` fired before the error, or not at all.
- Look at whether `return_exceptions=True` in `asyncio.gather` caught the error silently.

For frontend errors:
- Check the browser console first.
- Verify the SSE client closed correctly on `pipeline_done`/`pipeline_error`.
- Check whether the TypeScript types have drifted from the backend schemas.

---

## Step 3 — Isolate

Narrow to the smallest unit that reproduces the failure.

- Is it one agent, or all agents? (Try calling the agent directly with a fixture)
- Is it the prompt template, or the response parsing? (Log the raw Claude response)
- Is it the DB write, or the DB read? (Check the `JobResult` row directly in SQLite)
- Is it the SSE emission, or the SSE reception? (Check network tab)

Document your isolation findings — they go into the output.

---

## Step 4 — Fix

Make the minimal change that resolves the root cause.

Constraints:
- Do not change files unrelated to the bug
- Do not "clean up" nearby code while fixing — separate concerns, separate PRs
- If the fix requires touching a Pydantic schema, update the TypeScript types too and run the drift check
- If the fix touches the SSE contract (event names, payloads), update the SSE Client section in `CLAUDE.md`

---

## Step 5 — Verify

Prove the fix works before declaring done.

- Run the specific failing test: `pytest tests/path/to/test.py::test_name -v`
- Run the full suite: `make test`
- If the bug was a runtime issue (not covered by tests), add a regression test before closing
- For SSE bugs: manually trigger the pipeline and observe the event stream

---

## Output Format

After completing all five steps, produce:

```
Root Cause: <file>:<line> — one sentence describing what was wrong
Fix: one sentence describing what was changed and why it fixes it
Verification: list the commands run and their output (pass/fail)
Regression test: path to any new test added
```

Then add an entry to `tasks/lessons.md`:
```
## [date] <short title>
Pattern: what went wrong
Fix: what the correct approach is
Avoid: what not to do next time
```
