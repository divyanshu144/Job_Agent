# Session Handoff

<!-- 
HOW TO USE:
  - Overwrite this file at every checkpoint (do not append).
  - Git is the history — this file reflects current state only.
  - "Next Action" must be specific enough to act on immediately.
  - At session start: run `git status` AND `git log -1` to verify working tree
    and last commit match what this file describes. If they diverge, update
    this file to match reality before doing anything else.
  - Checkpoint triggers: task complete, wave/milestone done, user signals stop,
    unresolved blocker, context window ~70% utilized, 30+ min without an update.
-->

**Updated:** [YYYY-MM-DD]  
**Branch:** [branch name]  

---

## Current State

[What wave/feature is active. Which tasks are done vs. pending. One paragraph max.]

## Next Action

[The single next thing to do — specific enough to act on without reading anything else.
Example: "Run Task 3 of Wave 1: add make check to Makefile per tasks/todo.md line 22."]

## Why It Stopped

[Why work paused — awaiting confirmation, context limit, blocker, natural end of session.
If there is no special reason, write "Natural end of session."]

## In-Flight

[Uncommitted files or partial work. List file paths.
If nothing: "No uncommitted changes."]

## Open Questions

[Decisions deferred or questions requiring human input.
If none: "None."]

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | [N passing · X% coverage ✓ / FAILING — reason] |
| `make lint` | [✓ clean / FAILING — files and error codes] |
| `make check` | [✓ clean / FAILING / does not exist yet] |
