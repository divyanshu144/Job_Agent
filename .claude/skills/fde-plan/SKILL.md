# fde-plan — Feature Design & Planning Skill

**Trigger:** User asks to add a feature, build something new, or implement a change of 3+ steps.

**Hard rule:** This skill produces a plan only. Do NOT write any code. Do NOT create or edit files. The output is a structured document for the user to review and approve.

---

## Process

### Step 1 — Understand the Feature

Read the user's request carefully. Identify:
- What behaviour changes (new endpoint, new agent, new UI component, etc.)
- What existing components are affected
- Whether this touches the agent pipeline, the SSE contract, the DB schema, or the frontend types

If the request is ambiguous, ask one clarifying question before proceeding.

### Step 2 — Explore the Codebase

Use graph tools first (`semantic_search_nodes`, `query_graph`, `get_impact_radius`). Fall back to Grep/Read only if the graph doesn't cover what you need.

Identify:
- Files that will be created
- Files that will be modified (and which functions/classes specifically)
- Files that are downstream and may be affected but don't need changes

### Step 3 — Check for Constraint Violations

Before designing anything, verify the approach against `conventions.md`:
- Does it introduce any sync I/O in an async path?
- Does it construct DB sessions manually?
- Does it hardcode the API prefix?
- Does it bypass the agent output schema validation?

Flag any violations in the plan's Risks section.

### Step 4 — Output the Plan

Produce a structured plan in this exact format:

---

## Feature Plan: `<feature name>`

### Summary
One paragraph. What this feature does and why.

### Architecture Decisions
Bullet list of non-obvious choices made and why. Include trade-offs where relevant.

### Affected Files
| File | Change type | What changes |
|---|---|---|
| `backend/routes/foo.py` | Create | New router for X endpoint |
| `backend/schemas.py` | Modify | Add FooRequest, FooResponse schemas |
| ... | ... | ... |

### Implementation Steps
Ordered checklist. Each step is atomic and verifiable.
- [ ] Step 1: ...
- [ ] Step 2: ...
- [ ] Step 3: ...

### New Dependencies
List any new Python packages or npm packages required. If none, write "None."

### Risks
- Risk 1: ... (mitigation: ...)
- Risk 2: ... (mitigation: ...)

---

After outputting the plan, write it to `tasks/todo.md` and ask the user to approve before any implementation begins.
