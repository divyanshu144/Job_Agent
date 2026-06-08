# Subagent Brief Template

## Context (subagent reads first)
Read tasks/agent_memory.md and tasks/lessons.md before starting. Check
## Architecture Decisions for locked choices you must NOT reverse, even if a
stub's name or surrounding code suggests otherwise.

## Task
- Files to read:
- Exact behavior:
- Constraints (including what NOT to do):
- Verify command (e.g. make check):

## Before returning (required)
- Reach `make check` green before returning. No "should work."
- Thrash budget: after the first failed verify, take at most ONE targeted fix
  pass. If verify is still red, or you drift off-spec, STOP and return with what
  you found. Opus re-plans.
- If you solved a non-obvious problem, found a useful pattern, or hit an
  undocumented gotcha, append ONE concise entry (problem / root cause / solution)
  to the correct section of tasks/agent_memory.md.
