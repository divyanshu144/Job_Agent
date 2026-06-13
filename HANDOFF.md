# Session Handoff

**Updated:** 2026-06-13
**Branch:** main — clean, fully pushed (origin/main = `a4f733b`)

---

## Current State

**FDE-readiness goal (5 tasks) COMPLETE.** All shipped this session, each with
`make check` green and pushed individually:

| Task | Commit | What |
|---|---|---|
| 0 Housekeeping | `e99e37d` | docs/architecture-review committed + everything pushed |
| 1 Health + metrics | `cea8f44` | /health DB ping (200/503, exc class name only), /metrics via prometheus-fastapi-instrumentator, `llm_calls_total{agent,model}` in tracked_call |
| 2 Agent retry | `68f7201` | tenacity in BaseAgent._call: 3 attempts, exp+jitter, 529/timeout-only predicate, reraise=True; CRITICAL log at 5 consecutive failures (once per streak) |
| 3 Campaign UI (unit 8) | `5a9de23` | /campaign page: run-now (409→banner), 3s polling, run history, targets CRUD, materials via /history; drift checker now 11 classes |
| 4 Consistency evals | n/a | Already on main (`3c39fe0`); feat/evals-clean was integrated previously and deleted. No-op. |
| 5 Rate limiting | `f56a443` | slowapi: 10/min per-IP register/login, 100/min per-user (JWT sub key, IP fallback), 429+Retry-After, /health exempt |

The multi-tenant campaign feature (backend units 1–6 + frontend unit 8) is now
complete end to end.

**Whole-code review (10 findings) FIXED** — `4a56584` (backend) + `3a148dd`
(frontend): owner-scoped Phase-1 cache via find_cached_analysis (cross-tenant
hit + MultipleResultsFound), DB-enforced one-running-campaign-run (partial
unique index, migration 0007), zombie-run self-heal + queue-failure handling
(503), jwt-default CRITICAL startup signal, llm_calls(user_id,created_at)
index, settings create-race fix, cap-stop reason on completed runs, ApiError
status codes (409 branch, 429-tolerant polling). 472 passed, 82.04%.

**Second review round (Fable 5) — top 5 findings FIXED, TDD:**
`3fa0eb9` (batch 1): hard tenant boundary — regular users are refused
("complete your profile first", zero LLM spend) instead of ever falling back
to the shared profile_yaml_path/cv_path (admin-only); GET /profile mints the
per-user starter row; refresh rebuilds regular users from OWN data only;
repeat campaign runs count existing materials as drafted (already_generated
event code). `a4f733b` (batch 2): late queue messages can't re-execute
non-running runs; dispatch rolls back after a per-user failure; the
create_all stamp heuristic stamps to the matching revision (0006 when the
0007 indexes are missing) instead of blindly to head. 482 passed, 82.11%.

Deferred cleanup pass (user-ordered, NOT started): findings #5 (429 burns
poll attempts budget), #7 (usage IntegrityError NoResultFound mask), #8
(zombie 'running' visible in run history until next enqueue), #9 (run-now
503 mislabels non-queue errors), #10 (ApiError convention half-migrated).

## Next Action

Nothing in flight. Candidate follow-ups (not committed to):
- `GET/PATCH /api/campaign/settings` route pair → unlocks the settings section
  omitted from /campaign (enabled toggle + caps display)
- Per-run cost on CampaignRunResponse (join LLMCall by run window/user)
- Redis storage_uri for the rate limiter when going multi-worker
- Prometheus multiprocess mode if worker LLM metrics matter

## Why It Stopped

Goal complete — all 5 tasks green and pushed.

## In-Flight

None. Working tree clean.

## Open Questions

None.

## Verification Baseline

| Check | Result |
|---|---|
| `make check` | ✓ 466 passed, 1 deselected (integration eval) · 82.08% |
| frontend `npm run build` | ✓ clean (tsc + vite) |
| schema drift | ✓ 11 classes |
