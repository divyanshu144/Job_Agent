# RESOLVER.md — Skill Routing for JobFit Agent

When starting a task, match keywords from the user request against this table and load the indicated skill file(s). Load at most 2 files per response.

---

## Routing Table

| Keywords in request | Load skill |
|---|---|
| `feature`, `add`, `build`, `implement`, `new endpoint`, `new agent` | `.claude/skills/fde-plan/SKILL.md` |
| `bug`, `error`, `fix`, `broken`, `failing`, `exception`, `traceback` | `.claude/skills/debug-playbook/SKILL.md` |
| `route`, `endpoint`, `router`, `API`, `REST`, `response`, `request` | `.claude/skills/api-conventions/SKILL.md` |
| `review`, `check`, `audit`, `diff`, `PR`, `quality` | `.claude/skills/fde-review/SKILL.md` |
| `merge`, `pull request`, `ship`, `deploy`, `checklist` | `.claude/skills/pr-checklist/SKILL.md` |
| `convention`, `pattern`, `how do I`, `how should I`, `config`, `session`, `async` | `.claude/skills/conventions.md` |
| `leak`, `secret`, `credential`, `api key`, `filter-repo`, `filter-branch`, `rewrite history`, `remove from history` | `.claude/skills/git-leak-cleanup.md` |
| `pre-push`, `before push`, `safe to push`, `safe to ship`, `secrets scan`, `sensitive file` | `.claude/skills/pre-push-checklist.md` |

---

## Loading Rules

1. **conventions.md is near-default** — load it for any implementation task unless the task is purely a plan, review, or debug session. It contains cross-cutting invariants that apply to almost every code change in this project.

2. **Domain skills are conditional** — only load a domain skill when its keywords are present in the user's request. Don't load all skills speculatively.

3. **Load at most 2 files per response** — if multiple skills match, prefer the one most specific to the task type. `conventions.md` counts as one of the two slots.

4. **When in doubt, plan first** — if a request is ambiguous about scope, load `fde-plan/SKILL.md` and produce a plan before loading any implementation skill.

---

## Growth Rules

Add a new row to the routing table when:
- A new domain is added to the project (e.g., a new agent type, a new integration)
- A pattern comes up 3+ times in `tasks/lessons.md` — that pattern warrants its own skill file
- A new developer joins and asks the same question twice

When adding a row:
1. Create the skill file in `.claude/skills/<name>/SKILL.md`
2. Add the keyword row to this table
3. Update `CLAUDE.md` if the new domain changes any project-wide convention
