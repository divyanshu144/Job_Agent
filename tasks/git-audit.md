# Git State Audit
**Generated:** 2026-05-26  
**Branch at time of audit:** `feat/pipeline-optimisation`

---

## Section 1: Branch Overview

```
* feat/pipeline-optimisation  59d7613  updated   ← YOU ARE HERE
  main                        59d7613  updated
  remotes/origin/main         59d7613  updated
```

**Critical observation:** `feat/pipeline-optimisation` is at the **exact same commit as `main`**. The branch was created but nothing has been committed to it yet. There is zero divergence — it is just a renamed pointer to the same commit.

---

## Section 2: Current Uncommitted Changes

32 modified files + 2 untracked files. **None are staged.**

### Categorised by file

| File | Lines ±  | Category | Notes |
|---|---|---|---|
| `HANDOFF.md` | +31 / -37 | **DOCS** | Session state update (Wave 2 complete) |
| `RESOLVER.md` | +2 | **DOCS** | Two new routing rows added |
| `tasks/todo.md` | +10 | **DOCS** | Wave 2 tasks added and marked done |
| `.claude/skills/git-leak-cleanup.md` | new | **DOCS** | Untracked — new skill file |
| `.claude/skills/pre-push-checklist.md` | new | **DOCS** | Untracked — new skill file |
| `backend/agents/base.py` | +1 | **FORMATTING** | One blank line added before `tracked_call` call |
| `backend/agents/cold_email_agent.py` | +2 / -1 | **FORMATTING** | Line wrapping |
| `backend/models.py` | +12 / -4 | **FORMATTING** | Long `mapped_column(...)` lines wrapped; `'[]'` → `"[]"` quote normalisation |
| `backend/routes/auth.py` | +9 / -5 | **FORMATTING** | Line wrapping in constructors |
| `backend/routes/discovery.py` | +8 / -4 | **FORMATTING** | Line wrapping |
| `backend/routes/history.py` | +3 / -1 | **FORMATTING** | Line wrapping |
| `backend/routes/metrics.py` | +26 / -18 | **FORMATTING** | `RunCost(...)` constructor expanded across lines |
| `backend/routes/profile.py` | +5 / -2 | **FORMATTING** | Line wrapping |
| `backend/services/cost_calculator.py` | +1 / -1 | **FORMATTING** | Aligned spaces removed from dict literal |
| `backend/services/discovery.py` | +27 / -14 | **FORMATTING** | SQLAlchemy chained calls reformatted across lines |
| `backend/services/hn_client.py` | +9 / -5 | **FORMATTING** | Line wrapping |
| `backend/services/orchestrator.py` | +30 / -22 | **FORMATTING** | `JobResult(...)` and `Analysis(...)` constructors expanded |
| `backend/services/profile_builder.py` | +17 / -10 | **FORMATTING** | Line wrapping |
| `tests/test_database.py` | -1 | **FORMATTING** | Blank line removed |
| `tests/test_orchestrator/test_analysis_caching.py` | +24 / -8 | **FORMATTING** | Constructor expansion + blank lines before imports |
| `tests/test_orchestrator/test_phase1_direct.py` | +36 / -8 | **FORMATTING** | Constructor expansion |
| `tests/test_orchestrator/test_sse_sequence.py` | +30 / -12 | **FORMATTING** | Constructor expansion |
| `tests/test_routes/test_contacts.py` | +111 / -30 | **FORMATTING** | Fixture constructors expanded, blank lines added |
| `tests/test_routes/test_discovery_routes.py` | +29 / -9 | **FORMATTING** | Constructor expansion |
| `tests/test_routes/test_history.py` | +3 / -1 | **FORMATTING** | Line wrapping |
| `tests/test_routes/test_metrics.py` | +14 / -6 | **FORMATTING** | Constructor expansion |
| `tests/test_routes/test_status.py` | +3 / -1 | **FORMATTING** | Line wrapping |
| `tests/test_services/test_auth_service.py` | +5 / -3 | **FORMATTING** | Line wrapping |
| `tests/test_services/test_contact_discovery.py` | +57 / -19 | **FORMATTING** | Fixture constructors expanded |
| `tests/test_services/test_discovery.py` | +64 / -18 | **FORMATTING** | Constructor expansion + blank lines before imports |
| `tests/test_services/test_discovery_location.py` | +9 / -4 | **FORMATTING** | Line wrapping |
| `tests/test_services/test_hn_client.py` | +17 / -8 | **FORMATTING** | Line wrapping |
| `tests/test_services/test_instrumentation.py` | +5 / -3 | **FORMATTING** | Line wrapping |
| `tests/test_services/test_profile_builder.py` | +3 / -1 | **FORMATTING** | Line wrapping |

**Summary:** 29 FORMATTING files, 3 DOCS files, 2 untracked DOCS files.  
**Zero FEATURE changes in the working tree.** All logic changes are in the stash (see Section 4).

---

## Section 3: What's On Each Branch

```
git log main..feat/pipeline-optimisation --oneline
(no output)
```

`feat/pipeline-optimisation` has **zero commits ahead of main**. The branch exists in name only — it is pointing to the same commit as `main`. Nothing has been committed to it yet.

---

## Section 4: The Stash

**1 stash entry:**

```
stash@{0}: On main: wip: prompt caching + cost accounting
```

Contents (`git stash show stash@{0} --stat`):

| File | Lines ± |
|---|---|
| `backend/agents/base.py` | +7 / -1 |
| `backend/prompts/job_parser.md` | +2 / -3 |
| `backend/prompts/match_scorer.md` | +2 / -3 |
| `backend/services/cost_calculator.py` | +18 / -5 |
| `backend/services/discovery.py` | +40 / -24 |
| `backend/services/instrumentation.py` | +9 / -1 |
| `frontend/src/pages/Discover.tsx` | +4 / -2 |
| `frontend/vite.config.ts` | +1 / -1 |

**Category: FEATURE** — This is the prompt caching + cache cost tracking implementation that was attempted and reverted during a previous session. It includes:
- `base.py` — `cache_control` blocks added to `_call()`
- `cost_calculator.py` — cache read/write pricing tiers
- `instrumentation.py` — `cache_read_input_tokens` / `cache_creation_input_tokens` tracking
- `job_parser.md` / `match_scorer.md` — JD deduplication (remove `{jd}` from system prompt)
- `discovery.py` — substantial service changes (likely related to the caching + discovery work)
- `frontend/` — minor UI/config changes

**Overlap with working tree:** 3 files exist in both the stash and current working tree:
- `backend/agents/base.py` — stash has FEATURE changes; working tree has 1 FORMATTING line
- `backend/services/cost_calculator.py` — stash has FEATURE changes; working tree has 1 FORMATTING line
- `backend/services/discovery.py` — stash has FEATURE changes; working tree has FORMATTING changes

Popping the stash now **would likely cause merge conflicts** in all three files.

---

## Section 5: What Needs To Happen

### File → Branch mapping

| Files | Recommended branch |
|---|---|
| All 29 FORMATTING files (`backend/`, `tests/`) | `feat/pipeline-optimisation` — they're style-only, zero logic risk, go with the feature branch |
| `HANDOFF.md`, `RESOLVER.md`, `tasks/todo.md` | `chore/git-safety-skills` — harness/docs only |
| `.claude/skills/git-leak-cleanup.md` (untracked) | `chore/git-safety-skills` |
| `.claude/skills/pre-push-checklist.md` (untracked) | `chore/git-safety-skills` |
| Stash contents | New branch `feat/prompt-caching` — these are meaningful feature changes that deserve their own branch when you're ready to revisit |

### Cleanest commit sequence

1. **On `feat/pipeline-optimisation`** (you are already here):
   ```
   git add backend/ tests/
   git commit -m "style: apply ruff format across backend and tests"
   ```

2. **Create `chore/git-safety-skills`** from main:
   ```
   git stash  # temporarily stash formatting to get a clean switch, OR just leave it — it doesn't affect .claude/ or harness files
   git checkout main
   git checkout -b chore/git-safety-skills
   git add .claude/skills/git-leak-cleanup.md .claude/skills/pre-push-checklist.md RESOLVER.md HANDOFF.md tasks/todo.md
   git commit -m "chore: add git-leak-cleanup and pre-push-checklist skills"
   ```

3. **For the stash** — when ready, create a branch and pop it:
   ```
   git checkout main
   git checkout -b feat/prompt-caching
   git stash pop
   # resolve any conflicts, then commit
   ```

### On FORMATTING-only changes

All 29 backend/tests files changed by ruff format only. They contain zero logic changes and carry zero risk. They can be committed to `feat/pipeline-optimisation` as a standalone `style:` commit, or squashed into a future feature commit. They do not belong on `chore/` or `main` directly.

---

## Section 6: Risk Assessment

### Data loss risk

**HIGH** — all 32 modified files and 2 untracked files are **not staged and not committed**. Running any of the following would destroy this work:
- `git checkout .` or `git restore .`
- `git reset --hard HEAD`
- `git checkout <other-branch>` would warn about untracked files but could discard modified ones

**The two untracked skill files (`.claude/skills/*.md`) would be silently deleted** by `git clean -fd` with no warning. They are not tracked anywhere.

### Merge conflict risk

**MEDIUM** — if `git stash pop` is run:
- `backend/agents/base.py` — conflict likely (both stash and working tree modified)
- `backend/services/cost_calculator.py` — conflict likely
- `backend/services/discovery.py` — conflict likely (both modified significantly)

No conflicts between `feat/pipeline-optimisation` and `main` since the branch hasn't diverged.

### Test status (current working tree)

```
1 failed, 130 passed — 79.22% coverage ✓
```

**Failing test:** `tests/test_config.py::test_settings_defaults`  
**Cause:** Local `.env` sets `cv_path` to `/Users/divyanshu/jobfit-private-data/cv.pdf`, overriding the `"data/cv.pdf"` default the test expects. This is an environment issue, not a code regression. Not introduced by any current working-tree changes.

All other 130 tests pass. Coverage is above the 70% threshold.

---

## Summary Table

| Question | Answer |
|---|---|
| Commits ahead of main on feat branch | **0 — branch is empty** |
| Feature changes in working tree | **None — pure formatting** |
| Feature changes in stash | **Yes — prompt caching (8 files)** |
| Risk of data loss | **High if you run reset/checkout without staging first** |
| Stash pop conflicts | **Likely on 3 files** |
| Tests passing | **130/131 (1 pre-existing env failure)** |
