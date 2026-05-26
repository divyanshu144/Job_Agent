# LLM Cost Monitoring & Observability Design

**Date:** 2026-05-25
**Status:** Approved

## Goal

Track every LLM call made by JobFit Agent — cost, latency, cache hits — and surface the data on a `/costs` dashboard. Closes the "LLM cost optimization & monitoring" gap in the candidate profile and demonstrates production observability patterns.

## Architecture

```
backend/services/instrumentation.py   ← tracked_call() + write_llm_call()
    │  called by BaseAgent._call() and discovery.py directly
    └─► writes LLMCall row to DB (silently swallows DB errors — never breaks a call)

backend/services/cost_calculator.py   ← pricing table + calculate_cost()
    │  imported by instrumentation.py only
    └─► no knowledge of DB or HTTP

GET /api/metrics/costs/summary   ← totals: spend, calls, cache hit rate
GET /api/metrics/costs/runs      ← per-run list with pre-loaded per-agent data

/costs page
    ├── Summary bar (4 stat cards)
    ├── Runs table  (expandable rows — data pre-loaded, no extra fetch)
    └── Agent breakdown table (aggregate across all runs)
```

---

## Data Model

### New table: `llm_calls`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | TEXT (UUID) | No | PK |
| `agent_name` | TEXT | No | e.g. `"match_scorer"`, `"stage2_haiku"` |
| `model` | TEXT | No | e.g. `"claude-haiku-4-5-20251001"` |
| `input_tokens` | INTEGER | No | 0 when cache_hit=1 |
| `output_tokens` | INTEGER | No | 0 when cache_hit=1 |
| `cost_usd` | REAL | No | 0.0 when cache_hit=1 |
| `latency_ms` | INTEGER | No | wall-clock ms; 1 when cache_hit=1 |
| `cache_hit` | INTEGER | No | 1=cached, 0=real call |
| `analysis_id` | TEXT | Yes | FK → analyses; null for discovery |
| `run_id` | TEXT | Yes | FK → discovery_runs; null for analysis |
| `created_at` | TIMESTAMP | No | UTC |

**Known trade-off — cost_saved by cache:** Cache hit rows store 0 tokens so exact dollar savings are not computable from this table alone. The dashboard shows cache hit *count* and *rate* instead, which is honest and still tells the efficiency story. Exact savings would require storing the original call's token counts on the cache hit row — deferred as a future enhancement.

**Known trade-off — new direct Anthropic clients:** If a future service creates its own `AsyncAnthropic` instance instead of calling through `instrumentation.tracked_call()`, those calls will not be tracked. This pattern does not self-enforce; it requires a code review convention.

### Migration

Add `CREATE TABLE IF NOT EXISTS llm_calls (...)` as step 16 in `scripts/migrate.py`.

---

## Pricing Module

**File:** `backend/services/cost_calculator.py`

```python
COST_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_MILLION.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
```

Only `instrumentation.py` imports this module. No DB or HTTP imports here.

---

## Instrumentation

**File:** `backend/services/instrumentation.py`

Contains two public functions:

### `tracked_call()` — wraps every Anthropic API call

```python
async def tracked_call(
    client: AsyncAnthropic,
    agent_name: str,
    model: str,
    *,
    db: AsyncSession | None = None,
    run_id: str | None = None,
    analysis_id: str | None = None,
    **create_kwargs,
) -> anthropic.types.Message:
    start = time.monotonic()
    msg = await client.messages.create(model=model, **create_kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)
    if db is not None:
        await _write_llm_call(db, agent_name, model, msg.usage, latency_ms,
                              run_id=run_id, analysis_id=analysis_id)
    return msg
```

### `log_cache_hit()` — called by orchestrator on cache return

```python
async def log_cache_hit(
    db: AsyncSession,
    agent_name: str,
    model: str,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> None:
    await _write_llm_call(db, agent_name, model, usage=None, latency_ms=1,
                          cache_hit=True, run_id=run_id, analysis_id=analysis_id)
```

### `_write_llm_call()` — internal, always wrapped in try/except

```python
async def _write_llm_call(...) -> None:
    try:
        row = LLMCall(...)
        db.add(row)
        await db.commit()
    except Exception:
        pass  # never break a call due to a tracking failure
```

A failed DB write is silently swallowed. Agent responses are never blocked by instrumentation failures.

### Wiring

- `BaseAgent._call()` calls `tracked_call()`. Agent name from `type(self).__name__.lower()`.
- `discovery.py` Stage 2 call replaced with `tracked_call(..., agent_name="stage2_haiku")`.
- Orchestrator cache-hit path calls `log_cache_hit()` before returning.
- `db`, `run_id`, `analysis_id` are keyword-only with `None` defaults — all existing call sites that don't pass `db` continue to work unchanged.

---

## API

**File:** `backend/routes/metrics.py`

### `GET /api/metrics/costs/summary`

```json
{
  "total_cost_usd": 1.24,
  "total_calls": 312,
  "real_calls": 264,
  "cached_calls": 48,
  "cache_hit_rate": 0.154,
  "total_input_tokens": 980000,
  "total_output_tokens": 124000
}
```

Note: `cost_saved_by_cache_usd` is intentionally absent — see data model trade-off above.

### `GET /api/metrics/costs/runs`

Returns a list of runs (discovery runs + analyses), each with nested agent data pre-loaded (no separate fetch needed by the frontend):

```json
{
  "id": "...",
  "type": "discovery",
  "created_at": "...",
  "total_cost_usd": 0.042,
  "total_calls": 18,
  "cached_calls": 3,
  "latency_p50_ms": 1240,
  "agents": [
    { "agent_name": "stage2_haiku", "calls": 12, "cost_usd": 0.018, "avg_latency_ms": 890 },
    { "agent_name": "match_scorer",  "calls": 6,  "cost_usd": 0.024, "avg_latency_ms": 1620 }
  ]
}
```

**P50 latency:** Computed in Python — fetch `latency_ms` values for real calls in a run (cache hits excluded), sort, pick median. Capped at 500 rows per run to bound memory. At current scale this is never reached; the cap is documented as a known scaling boundary.

Both endpoints require `Depends(get_current_user)`.
Register router in `backend/main.py`.

---

## Frontend

**File:** `frontend/src/pages/Costs.tsx`

**Data loading:** `getCostSummary()` and `getCostRuns()` are called on mount. Agent breakdown is pre-loaded in the runs response — expanding a row is a local state toggle, not a network request.

**Three sections:**

**1. Summary bar** — four stat cards:
- Total spent (`$1.24`)
- Total LLM calls (`312`)
- Cache hit rate (`15%`)
- Real calls made (`264`)

**2. Runs table** — one row per discovery run or analysis: date, type, calls, cost, P50 latency ms, cache hits. Clicking a row toggles an inline agent breakdown (client-side expand/collapse, no fetch).

**3. Agent breakdown** — aggregate table across all runs: agent name, total calls, total cost, avg latency, % of total spend.

**New types** in `frontend/src/types/index.ts`:
```typescript
export interface CostSummary {
  total_cost_usd: number; total_calls: number; real_calls: number;
  cached_calls: number; cache_hit_rate: number;
  total_input_tokens: number; total_output_tokens: number;
}
export interface AgentCost { agent_name: string; calls: number; cost_usd: number; avg_latency_ms: number; }
export interface RunCost {
  id: string; type: "discovery" | "analysis"; created_at: string;
  total_cost_usd: number; total_calls: number; cached_calls: number;
  latency_p50_ms: number; agents: AgentCost[];
}
```

**API methods in `client.ts`:** `getCostSummary()`, `getCostRuns()`.

**Nav:** Add "Costs" link in `App.tsx` nav, protected route at `/costs`.

---

## Known Limitations / Future Work

| Item | Severity | Note |
|---|---|---|
| Cost saved by cache not computable | Low | Show hit count instead; exact savings need original token data stored on cache hit rows |
| Direct Anthropic clients bypass tracking | Medium | Code review convention + comment at the danger point in `discovery.py`: `# must use tracked_call() — not raw client.messages.create()` |
| P50 capped at 500 rows | Low | Fine at current scale; note for future if discovery runs grow large |
| No retention/pruning | Low | `llm_calls` grows forever; consider pruning rows older than 90 days once table is large |

---

## What This Teaches You

| Pattern | Where it appears |
|---|---|
| Instrument at the lowest shared layer | `tracked_call()` — one function captures all agents |
| Separate pricing from tracking | `cost_calculator.py` vs `instrumentation.py` |
| Never let observability break the hot path | `try/except` in `_write_llm_call()` |
| Optional DB context — zero breaking changes | `db=None` keyword-only default |
| Cache hit rate as a first-class metric | `cache_hit` column + stat card |
| P50 latency without native SQL percentiles | Python sort + median on fetched rows |

---

## Files

| File | Action |
|---|---|
| `backend/services/cost_calculator.py` | Create — pricing table + `calculate_cost()` |
| `backend/services/instrumentation.py` | Create — `tracked_call()`, `log_cache_hit()`, `_write_llm_call()` |
| `backend/models.py` | Add `LLMCall` ORM model |
| `scripts/migrate.py` | Add step 16: `llm_calls` table |
| `backend/agents/base.py` | Modify `_call()` to delegate to `tracked_call()` |
| `backend/services/orchestrator.py` | Pass `db`/`analysis_id` through to agents; call `log_cache_hit()` on cache return |
| `backend/services/discovery.py` | Replace direct `_anthropic_client.messages.create` with `tracked_call()` |
| `backend/routes/metrics.py` | Create — two cost endpoints |
| `backend/main.py` | Register metrics router |
| `frontend/src/types/index.ts` | Add `CostSummary`, `RunCost`, `AgentCost` |
| `frontend/src/api/client.ts` | Add `getCostSummary()`, `getCostRuns()` |
| `frontend/src/pages/Costs.tsx` | Create — dashboard page |
| `frontend/src/App.tsx` | Add `/costs` route + nav link |
| `tests/test_services/test_cost_calculator.py` | Create |
| `tests/test_services/test_instrumentation.py` | Create |
| `tests/test_routes/test_metrics.py` | Create |
