# Observability and Cost

## LLMCall Cost Ledger

`LLMCall` in `backend/models.py` is the cost ledger for model usage.

Rows are written by `tracked_call()` in `backend/services/instrumentation.py`.

Captured fields include:

- `agent_name`,
- `model`,
- `input_tokens`,
- `output_tokens`,
- `cost_usd`,
- `latency_ms`,
- `cache_hit`,
- `cache_creation_tokens`,
- `cache_read_tokens`,
- `analysis_id`,
- `run_id`,
- `user_id`.

Cost calculation lives in `backend/services/cost_calculator.py`.

Why this matters: cost is not left to the provider dashboard. It is queryable by run, analysis, user, agent, and model.

## PipelineEvent Tracing

`PipelineEvent` in `backend/models.py` records workflow events.

Events are written by helpers in `backend/services/instrumentation.py`:

- `new_trace_id()`
- `span()`
- `log_event()`

Event fields include:

- `trace_id`,
- `kind`,
- `name`,
- `status`,
- `duration_ms`,
- `detail`,
- `analysis_id`,
- `run_id`.

The orchestrator uses spans around agent execution. Discovery uses events for tool calls and failures. `BaseAgent._log_retry()` records self-correction attempts as retry events.

## Cache Hits

The analysis cache key is implemented in `analysis_cache_key()` in `backend/services/orchestrator.py`.

It hashes:

- job description text,
- profile content hash from `profile_content_hash()`.

If a complete matching analysis exists, phase 1 is skipped and `log_cache_hit()` writes an `LLMCall` row with `cache_hit=True` and zero cost.

Note: this is application-level result caching. It is distinct from Anthropic prompt caching.

## Cost Dashboard

Cost routes are implemented in `backend/routes/metrics.py`:

- `GET /api/metrics/costs/summary`
- `GET /api/metrics/costs/runs`

The dashboard aggregates:

- total cost,
- total calls,
- cached calls,
- cache hit rate,
- input/output tokens,
- Haiku cost,
- counterfactual Sonnet cost,
- tiering savings,
- prompt cache token accounting.

The frontend page is `frontend/src/pages/Costs.tsx`.

## Current Observability Gaps

Current strengths:

- Per-call token/cost accounting.
- Per-agent spans.
- Trace IDs in JSON logs.
- Fail-open telemetry writes.
- Cost dashboard.

Gaps:

- No distributed tracing backend.
- No UI for inspecting `PipelineEvent` traces.
- No alerting or SLOs.
- Discovery in-process background tasks can fail with limited operational visibility.
- Celery task IDs are not persisted on `CampaignRun`.
- Cost caps are enforced for campaign flows but not globally for every interactive LLM call.

Recommended improvements:

1. Store Celery task IDs on durable run records.
2. Add an admin trace view keyed by `analysis_id` or `run_id`.
3. Add global budget checks before all user-attributed LLM calls.
4. Emit structured lifecycle events for discovery and campaign runs.
