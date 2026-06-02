---
description: Find recurring patterns in tasks/lessons.md (3+ occurrences) and draft a skill + RESOLVER mapping for human approval
allowed-tools: Read, Grep, Glob
---

# Promote Lesson → Skill

You are auditing `tasks/lessons.md` to find patterns worth promoting into a reusable skill.

## Hard rule

**Propose only. Write nothing.** Do NOT create or edit any file (no skill file, no
`RESOLVER.md` edit) in this command. Your entire output is a proposal the human
reviews. Only after they explicitly approve (in a later turn) may files be written.

## Steps

1. **Read** `tasks/lessons.md` in full.

2. **Cluster by root cause.** Group entries by the *meaning* of their `Pattern:`
   field, not exact text — these are prose, so judge semantic similarity (e.g.
   "null-safe access on external API responses" and "explicit null vs missing key"
   are the same root cause). A cluster qualifies only at **3 or more** entries.

3. **If no cluster reaches 3**, say so plainly, list the largest clusters and their
   counts, and stop. Do not invent a skill from thin evidence.

4. **For each qualifying cluster**, draft (in your reply, not on disk):
   - **Proposed skill file** — full path `.claude/skills/<kebab-name>/SKILL.md` plus
     its complete proposed contents, following the style of the existing skills
     (trigger line, hard rule if any, numbered process or checklist, output format).
     Cite the source `lessons.md` entries (dates + one-line summaries) it generalises.
   - **Proposed RESOLVER.md row** — the exact `| keywords | skill path |` line to add,
     plus where it slots into the routing table. Pick keywords a future request would
     actually contain.

5. **Stop for approval.** End with a short, explicit question:
   "Approve writing these N file(s) and the RESOLVER row? (yes / edit / no)".
   Take no further action until the human answers.

## Notes

- Respect `RESOLVER.md`'s own Growth Rules: a pattern earns a skill at 3+ occurrences.
- Prefer one focused skill per root cause over a grab-bag skill.
- If a matching skill already exists, propose *augmenting* it instead of creating a new one.
