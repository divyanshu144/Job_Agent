# Observability & Instrumentation Audit — JobFit Agent

**Date:** 2026-06-01
**Scope:** read-only audit of current observability vs. target wishlist. No code changed.
**Method:** verified against `backend/` source; `file:line` evidence cited. Hypotheses in the
brief were treated as unverified and corrected where stale.

---

## Status table

| # | Item | Status | Evidence | Gap |
|---|------|--------|----------|-----|
| 1 | Structured logging | **PARTIAL** | `reed_client.py:12`, `adzuna_client.py:12`, `discovery.py:27`, `profile_builder.py:18` each do `logging.getLogger(__name__)`. No central config in `main.py`/`config.py` (verified absent). No JSON formatter, no `dictConfig`/`basicConfig`. | Ad-hoc stdlib logging in 4 service files only; agents, orchestrator, and all routes log nothing. No structured substrate, no JSON output, no central config, no log level setting, no correlation fields. Logs go to the default root handler (unstructured stderr, WARNING+). |
| 2 | Trace IDs (run_id) | **PARTIAL** | `run_id` generated as `DiscoveryRun.id` and threaded discovery-side: `discovery.py:112` (`_stage2_check`→`tracked_call`), `discovery.py:212` (`_run_phase1`). Lands on `LLMCall.run_id` (`models.py:88`). Manual paths thread `analysis_id` instead: `orchestrator.py:232`, `:321`, `:343`. | `run_id` is consistently threaded **only on the discovery path**. Manual `run_evaluate_pipeline`/`run_generate_pipeline` never set `run_id` (by design — they use `analysis_id`). Result: two separate correlation columns (`run_id`, `analysis_id`), no single unified trace id, and neither appears in logs because there are no structured logs to correlate against. |
| 3 | Per-node traces | **REFRAME** | No LangGraph/LangChain anywhere in code (only design-doc mentions: `docs/.../2026-05-20-jobfit-agent-design.md:157`). Node boundaries are SSE events only: `orchestrator.py:206,233,238,241,255` (`pipeline_start/agent_start/agent_done/pipeline_error/pipeline_done`). Per-LLM latency exists (`LLMCall.latency_ms`, `instrumentation.py:26`) but no per-agent span. | No graph framework to instrument. **Reframe to: emit per-agent spans from the existing orchestrator** (start/end/status/duration per agent), persisted alongside `LLMCall`. SSE events are ephemeral and carry no timing/status record. |
| 4 | Tool call logs | **PARTIAL** | LLM calls tracked (success only) with latency via `tracked_call` (`instrumentation.py:14-53`), incl. discovery Haiku (`discovery.py:107`). External HTTP clients log **errors only**, no duration/args/result: `adzuna_client.py:50`, `hn_client.py:49,101`, `contact_discovery.py:71-73`. No Anthropic tool-use/function-calling (agents send system+user, parse JSON text). | Individual external API calls (Reed/Adzuna/HN/Hunter/GitHub) are not logged with args/result/duration — only failures are warned. LLM "tool" calls are tracked but only on success (see #5). |
| 5 | Failure reasons | **MISSING** (structured) | `pipeline_error` carries only `str(e)`: `orchestrator.py:241,279,285,332,357`. `JobResult.error` column exists (`models.py:156`) but is **never written** (verified — no `JobResult(...error=)` writes). Discovery failures log warnings only: `discovery.py:187,215`. Failed LLM calls write no row (tracked_call writes *after* a successful `create()`, `instrumentation.py:25`). | No persistent, structured failure record (exception type / agent / phase / timestamp / run/analysis id). Failure detail lives only in ephemeral SSE strings and stdlib warnings. `asyncio.gather` exceptions are **not** silently swallowed in `_run_discovery_task:299` / `_run_source_task:420` / Phase-2 generate `orchestrator.py:354` (all logged/surfaced) — except `_run_all_discovery_task:454`, which discards gather results. |
| 6 | Retry attempts | **PARTIAL** | No `tenacity`, no custom backoff, no `max_retries` override anywhere (verified). Anthropic clients constructed without `max_retries`: `base.py:25`, `discovery.py:31` → **SDK default `max_retries=2` applies implicitly**. httpx clients set only timeouts, no retry: `adzuna_client.py:33`, `hn_client.py:36,62`, `contact_discovery.py:64`. The `"retry": True` in `contacts.py:52,130` is a client hint, not server retry. | LLM calls retry implicitly (SDK default) but it is **invisible** — no logging of attempt count, backoff, or final failure cause. External HTTP calls have **no** retry at all. No tuning knob, no observability of retries. |
| 7 | Token / cost / latency | **BUILT** | Persisted per call on `LLMCall` (`models.py:73-91`): tokens, `cost_usd`, `latency_ms`, cache_hit, cache tokens, `run_id`, `analysis_id`, `created_at`. Written by `tracked_call` (`instrumentation.py:31-52`). Exposed via `routes/metrics.py`: `/metrics/costs/summary` (aggregate cost, calls, cache-hit rate, tokens, Haiku tiering savings, prompt-cache savings) and `/metrics/costs/runs` (per-run & per-analysis breakdown + per-agent `_agent_breakdown` + `_p50_latency`). Schemas `CostSummary/RunCost/AgentCost` (`schemas.py`). | Strong. Gaps: latency is **per-LLM-call only** — no end-to-end pipeline wall-clock; failed calls excluded from cost/latency entirely (#5); only p50 (no p95/p99); metrics are admin-only; `_p50_latency` loads up to 500 rows into Python. |
| 8 | User feedback loops | **Feedback: BUILT (capture). Evals: BUILT (validators); no feedback-consuming scorer yet** | Feedback capture added (`Feedback` model + `routes/feedback.py` + frontend control). Evals live in `backend/evals/validators.py` (per-agent `validate_*`) + `scripts/consistency_check.py` + `tests/test_evals/` — integrated from `feat/evals-clean` (CORRECTION: an earlier pass wrongly called these "lost/uncommitted"; they were on a sibling branch not present in the local repo at audit time and are now merged). Plus discovery gating heuristics (`_stage1_pass`, `_match_profiles`). | No scorer yet *consumes* `Feedback` to produce quality scores — the `backend/evals/__init__.py` hook documents where that goes. That scorer is the remaining gap. |

---

## Cross-cutting observations

- **Two correlation ids, no unifying spine.** `LLMCall` carries both `analysis_id` (manual paths) and
  `run_id` (discovery). Each is threaded correctly on its own path, but nothing ties a request's logs,
  spans, failures, and cost rows together — partly because there are no structured logs at all.
- **Cost/latency is the one mature pillar.** Everything else (logs, traces, failures, retries, feedback)
  is either ad-hoc or absent. The cheapest wins stamp new signals onto the existing `tracked_call` /
  `LLMCall` spine and a new structured-log substrate keyed on the same ids.
- **Failures are the biggest blind spot.** A failed LLM call or external fetch produces no durable record
  at all (no cost row, no failure row, only an ephemeral SSE string or a WARNING to stderr). The
  `JobResult.error` column is already there to receive it but is unused.
- **LangGraph reframe.** Per-node tracing should be implemented as orchestrator-emitted per-agent spans,
  not by adopting a graph framework.

---

## Inputs to the plan (Step 2)

Foundation → cheap stamps → unify ids → feedback track:
1. **Structured logging keyed on run_id/analysis_id** (`instrumentation.py`) — the substrate.
2. Stamp onto it: **structured failure capture** (use `JobResult.error` + a failure record), **external
   tool-call logs** (duration/status), **retry events**, **per-agent spans**.
3. Ensure **cost rows and log/span records share the same correlation id**.
4. **User feedback** as its own track, wired into a (new) evals surface.

---

## Open Questions

1. **`pipeline_events` unbounded growth on SQLite.** The new events table grows with every
   pipeline run with no retention/pruning. Acceptable for the current single-user deployment;
   revisit (TTL prune or rotation) if it grows or the app goes multi-user.
2. **Evals → feedback scorer (not "lost").** Correction: `backend/evals/validators.py` (six
   `validate_*` fns) + `scripts/consistency_check.py` + `tests/test_evals/` were on `feat/evals-clean`
   (not in the local repo at audit time) and are now integrated. The remaining gap is a scorer that
   *consumes* `Feedback` rows to produce quality scores — see the hook in `backend/evals/__init__.py`.
