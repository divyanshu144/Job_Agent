# Session Handoff

**Updated:** 2026-06-08
**Branch:** feat/boot-alembic-upgrade — committed, not merged

---

## Current State

**App boot now runs `alembic upgrade head` instead of `create_all`** (implemented by a Sonnet 4.6
subagent under Opus review — first use of the delegate pattern). `make check` green (**276 passed**).

- `backend/database.py`: `init_db()` now `await asyncio.to_thread(_run_upgrade, settings.database_url)`;
  `_run_upgrade(url)` builds an Alembic `Config` from `alembic.ini` + URL and runs `command.upgrade(cfg,"head")`.
  `create_all` removed from the boot path. (Gotcha: alembic env.py calls `asyncio.run` internally → must
  run on a thread; logged in agent_memory.md.)
- `create_all` remains ONLY in `tests/conftest.py` (test bootstrap untouched).
- `tests/test_startup.py`: clean postgres:16 container → `_run_upgrade(url)` → asserts `users` +
  `alembic_version` exist.

## ⚠️ Branch pile-up — needs consolidation

Five unmerged branches now stack/diverge off `main` (all green individually):
1. `feat/postgres-migration` — **already merged to main (PR #11)**; ignore.
2. `fix/cold-email-tone` (off main) — human-tone cold_email prompt.
3. `feat/contacts-gmail-send` (off main) — real Gmail send for `/contacts/{id}/send` (+ `gmail_service.py`).
4. `chore/agent-memory-infra` (off main) — agent_memory.md + brief_template + CLAUDE.md.
5. `feat/boot-alembic-upgrade` (off #4) — THIS branch (boot → alembic upgrade).

#5 is stacked on #4 (needed agent_memory.md present). 2/3/4 are independent off main. Recommend merging
in order: 4 → 5, then 3, then 2 (no overlaps expected; run `make check` after each).

Note: agent_memory.md says "Manual send … is fine" (true once #3 merges) — currently `main`'s send is
still the 503 stub.

## Next Action

Decide merge order for the 4 open branches + push. Then resume feature work.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` (this branch) | ✓ 276 passed, 1 deselected |
| boot path | ✓ test_startup: clean PG → alembic upgrade head → tables present |
