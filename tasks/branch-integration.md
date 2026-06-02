# Branch Integration — Audit & Plan

**Date:** 2026-06-02 · **Base:** `main` = `3f493d8` (Batch API, PR #7) · **Read-only pass — nothing merged.**

## Batch-API surface on main (what new work must avoid colliding with)
`2d3e5a8 → 3f493d8` changed: `models.py`, `routes/discovery.py`, `schemas.py`,
`services/batch_processor.py` (new), `cost_calculator.py`, `services/discovery.py`,
`services/instrumentation.py`, `tasks/lessons.md`, + batch tests.

## Step 1 — Branch inventory

| Branch | ahead/behind main | Contents (key files) | Completeness | Conflict risk |
|---|---|---|---|---|
| **feat/history** `86e9db2` | 7 / 12 | **Full stack** = harness hooks + observability + analysed-jobs-on-Analyse-page. Touches `instrumentation.py`, `discovery.py`, `orchestrator.py`, `models.py`, `schemas.py`, `base.py`, `config.py`, `main.py`, `database.py`, `routes/feedback.py`, `backend/evals/__init__.py` (stub), frontend (`AnalyseJob`, `Results`, `client`, `types`), `scripts/backfill_analysis_meta.py`, tests. | **Done** — `make check` 185 passed this session. | **HIGH** vs Batch at `instrumentation.py` + `discovery.py` (both ADD functions); additive-overlap `models.py`/`schemas.py`/`lessons.md`. Vs evals-clean: `backend/evals/__init__.py` collision, `schemas.py`, `types`. |
| **chore/harness-hooks** `2711a7c` | 6 / 12 | **= feat/observability (identical commit).** Harness hooks + full observability. | Done. | **Contained in feat/history — do NOT merge separately.** |
| **feat/observability** `2711a7c` | 6 / 12 | **Duplicate of chore/harness-hooks** (same tip). | Done. | Contained in feat/history — skip. |
| **feat/evals-clean** `3c39fe0` | 1 / 12 | Real evals: `backend/evals/validators.py` (204 lines), `scripts/consistency_check.py`, `tests/test_evals/{test_consistency,test_validators}.py`, `Makefile` (`eval-consistency`), `pyproject.toml`, touches 6 agents + `schemas.py` + `types`. | Looks complete; **not yet `make check`-verified** (needs checkout). | **LOW** — touches **none** of Batch's logic files (instrumentation/discovery/models/cost verified clean). Overlap only: `backend/evals/__init__.py` (vs history stub), `schemas.py`, `types` (additive). |
| **feat/referral-clean** `24cf557` | 2 / 12 | Referral system + **removes GitHub-client scraping**. `auth.py`, `profile.py`, `profile_builder.py`, `github_client.py`, `models.py`, `config.py`, `database.py`, `schemas.py`, frontend (`AuthContext`, `ProfileSetup`, `Register`), broad test updates. | Has a test-fix commit → appears complete; unverified. | **MED–HIGH** — `models.py`/`schemas.py`/`config.py`/`database.py` vs both Batch and history-stack; distinct product feature. |
| **feat/prompt-caching** `4e88f98` | 11 / **38** | OLD mixed stack: prompt caching + referral + evals + Reed/Adzuna clients + `_inject` fix + Phase-2 sessions. | **Superseded** — prompt caching already in main; evals lives in feat/evals-clean; discovery clients already in main. | Moot — recommend drop after verify. |
| **feat/job-board-scrapers** `4e88f98` | 11 / 38 | **Identical to feat/prompt-caching** (same tip). | Duplicate. | Drop. |

### Key findings
1. **The "four branches" are two content sets:** merge **feat/history** (brings harness + observability + history) and **feat/evals-clean**. `chore/harness-hooks` and `feat/observability` are the same commit, already inside feat/history.
2. **evals-clean is near-clean** — zero overlap with Batch-API logic; only a trivial `backend/evals/__init__.py` collision with history's stub.
3. **The only real merge conflict is feat/history's observability vs Batch API** in `instrumentation.py` and `discovery.py` (both ADD functions — resolvable by keeping both).
4. **feat/prompt-caching ≡ feat/job-board-scrapers**, both stale/superseded.

## Step 2 — Integration plan (known-good only)

**Mechanism (recommended): integration branch, merge-based.** Keep `main` untouched until green.
```
git switch -c integration/consolidate main        # off 3f493d8
git merge feat/evals-clean                         # near-clean; resolve evals __init__ + schemas/types
git merge feat/history                             # the conflict step (see below)
# resolve, make check, iterate
# only when green:  git switch main && git merge --ff-only integration/consolidate
```
**Order:** evals-clean **first** (establishes the canonical `backend/evals/` package), then feat/history.
Merge order doesn't change conflict content (unlike rebase); evals-first just means the stub-drop happens
during the history merge.

**Tradeoff vs stacked rebase:** a rebase of the history stack onto main gives linear history but forces you
to re-resolve the instrumentation/discovery conflicts at *each* of the 6 replayed commits. The merge
approach resolves them **once**. Recommend merge unless linear history is required.

### Conflict resolution checklist (during `git merge feat/history`)
- **`backend/services/instrumentation.py`** — keep BOTH: our `trace_id`/`log_event`/`span`/
  `configure_logging`/`JsonLogFormatter` AND Batch's `log_batch_llm_call`.
- **`backend/services/discovery.py`** — keep BOTH: our trace/span/failure/tool-span additions AND Batch's
  `run_batch_discovery`/`_run_batch_discovery_task`. Watch the shared `_anthropic_client` (we set
  `max_retries`) and `_process_job`.
- **`backend/models.py`** — keep `PipelineEvent` + `Feedback` + Analysis cols **and** `DiscoveryBatch` (additive).
- **`backend/schemas.py`** — keep Feedback/AnalysisSummary fields, evals schemas, and Batch schemas.
- **`backend/evals/__init__.py`** — **evals-clean is canonical.** Drop our stub's content; keep the real
  package. Re-point the feedback "evals hook" comment (routes/feedback.py + the `__init__` docstring) at the
  real `validate_*` functions in `validators.py`.
- **`tasks/lessons.md`** — both append; keep both blocks.
- **`tasks/observability-audit.md` #8** — fix the framing: evals are **not lost**, they live in
  `feat/evals-clean` (now merged); remove the "scaffolded-but-lost" claim.
- **`frontend/src/types/index.ts`** — keep both sets of added types.

### Verification (each step)
`make check` (fmt+lint+mypy+schema-drift+pytest ≥70) after each merge; `cd frontend && npx tsc --noEmit`.
Expect to re-run after resolving instrumentation/discovery. Do **not** touch `main` until green.

## Unassessed siblings — keep / drop / defer (your call)
- **feat/referral-clean** — *DEFER (decide as its own feature).* A real, seemingly-complete feature (referral
  system + removing GitHub scraping) but **unrelated** to this observability/history/evals consolidation, and
  it removes `github_client` scraping which other code/profile-building depends on — a product decision, not a
  mechanical merge. Recommend a separate review/integration pass, not this one.
- **feat/prompt-caching** — *DROP after verify.* Superseded: prompt caching is already in main; its evals are
  an older copy of feat/evals-clean; its discovery clients already landed. Behind main by 38. Confirm no
  unique commit, then delete.
- **feat/job-board-scrapers** — *DROP.* Identical tip to feat/prompt-caching (`4e88f98`); same superseded content.

## Safety-hook flags (run yourself if blocked)
- The swarm-safety PreToolUse hook blocks **force-push** and other destructive patterns. Plain
  `git merge` / `git commit` / non-force `git push` should pass. If any step needs `git push --force*`,
  `git reset --hard`, or branch **deletion** (`git branch -D`, `git push origin --delete`), the hook will
  block the agent — **you run those** (dropping the superseded branches will need this).
- Final `git switch main && git merge --ff-only integration/...` and `git push origin main` are non-force;
  flag for your explicit go-ahead anyway since they touch `main`.

## Open decisions for approval
1. Confirm **merge-based integration branch** (vs stacked rebase).
2. Confirm scope = **feat/history + feat/evals-clean only** this pass; referral deferred; prompt-caching/
   job-board-scrapers dropped after verify.
3. Who runs the branch deletions (hook-blocked for the agent).
