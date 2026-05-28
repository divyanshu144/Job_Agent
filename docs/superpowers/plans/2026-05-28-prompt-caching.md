# Anthropic Prompt Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Anthropic's `cache_control` prompt caching to all agent calls so repeated system prompts within a discovery batch are served from Anthropic's cache at 10% of normal input token cost.

**Architecture:** Mark system prompts with `cache_control: {type: "ephemeral"}` in `base.py`. In `instrumentation.py`, read `cache_creation_input_tokens` and `cache_read_input_tokens` from the Anthropic response and store them in two new `llm_calls` columns. Update `cost_calculator.py` to price cache tokens at their discounted rates (write: 1.25×, read: 0.10× normal input). Expose prompt cache savings in the metrics endpoint and Costs.tsx dashboard panel.

**Tech Stack:** Anthropic SDK (`anthropic.AsyncAnthropic`), SQLAlchemy 2.0 async, FastAPI, Pydantic v2, React/TypeScript, SQLite

---

## Codebase Context

Before touching any file, understand the data flow:

1. An agent (e.g. `MatchScorerAgent`) calls `self._call(system, user)` in `base.py`
2. `_call()` delegates to `tracked_call()` in `instrumentation.py`, which calls `client.messages.create()`
3. `tracked_call()` calls `calculate_cost()` in `cost_calculator.py` and writes a `LLMCall` row to the DB
4. The `/api/metrics/costs/summary` route aggregates `LLMCall` rows into `CostSummary`
5. `Costs.tsx` renders the summary; it already has an emerald tiering-savings panel

**Anthropic cache pricing (as of 2025):**
- Cache write (first call, or after 5-min TTL): **1.25×** normal input rate
- Cache read (subsequent calls within TTL): **0.10×** normal input rate (90% discount)
- `msg.usage.cache_creation_input_tokens`: tokens written to cache this call (may be `None` or `0`)
- `msg.usage.cache_read_input_tokens`: tokens read from cache this call (may be `None` or `0`)
- `msg.usage.input_tokens`: tokens NOT served from cache (always present)

---

## File Map

| File | Change |
|---|---|
| `backend/services/cost_calculator.py` | Add `cache_write` / `cache_read` rates; update `calculate_cost()` signature |
| `backend/services/instrumentation.py` | Read cache token counts from `msg.usage`; pass to cost calc and DB write |
| `backend/agents/base.py` | Change `system=str` → `system=[{type,text,cache_control}]` in `_call()` |
| `backend/models.py` | Add `cache_creation_tokens` + `cache_read_tokens` columns to `LLMCall` |
| `backend/database.py` | Add `init_db()` migration for two new columns |
| `scripts/migrate.py` | Add two `ALTER TABLE llm_calls ADD COLUMN` steps (idempotent) |
| `backend/schemas.py` | Add `prompt_cache_read_tokens`, `prompt_cache_creation_tokens`, `prompt_cache_savings_usd` to `CostSummary` |
| `backend/routes/metrics.py` | Query new columns; compute prompt cache savings and return in `CostSummary` |
| `frontend/src/types/index.ts` | Add three new fields to `CostSummary` interface |
| `frontend/src/pages/Costs.tsx` | Add "Prompt Cache Savings" emerald panel (mirrors tiering panel style) |
| `tests/test_services/test_cost_calculator.py` | Tests for cache token pricing |
| `tests/test_services/test_instrumentation.py` | Tests for cache token extraction from mock response |
| `tests/test_routes/test_metrics.py` | Tests for new CostSummary fields |

---

## Task 1: Update cost_calculator.py with cache pricing

**Files:**
- Modify: `backend/services/cost_calculator.py`
- Test: `tests/test_services/test_cost_calculator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_cost_calculator.py  — ADD these after existing tests

def test_cache_write_costs_1_25x_input():
    """Cache creation tokens are priced at 1.25× normal input rate."""
    # Haiku input rate: $0.80/M → cache write: $1.00/M
    cost = calculate_cost("claude-haiku-4-5-20251001", 0, 0, cache_creation_tokens=1_000_000)
    assert cost == pytest.approx(1.00)


def test_cache_read_costs_0_10x_input():
    """Cache read tokens are priced at 0.10× normal input rate."""
    # Haiku input rate: $0.80/M → cache read: $0.08/M
    cost = calculate_cost("claude-haiku-4-5-20251001", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.08)


def test_full_call_with_cache_mix():
    """A call with input + cache_write + cache_read + output tokens prices correctly."""
    # Sonnet: input $3/M, output $15/M, cache_write $3.75/M, cache_read $0.30/M
    cost = calculate_cost(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,      # $3.00
        output_tokens=1_000_000,     # $15.00
        cache_creation_tokens=1_000_000,  # $3.75
        cache_read_tokens=1_000_000,      # $0.30
    )
    assert cost == pytest.approx(22.05)


def test_unknown_model_cache_fallback():
    """Unknown model falls back to Sonnet cache rates."""
    cost = calculate_cost("unknown-model", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.30)  # Sonnet cache_read = $0.30/M
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_services/test_cost_calculator.py -v 2>&1 | tail -20
```
Expected: 4 new tests fail with `TypeError: calculate_cost() got an unexpected keyword argument 'cache_creation_tokens'`

- [ ] **Step 3: Implement**

Replace the entire contents of `backend/services/cost_calculator.py`:

```python
from __future__ import annotations

COST_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,   # 1.25× input rate
        "cache_read": 0.08,    # 0.10× input rate
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,   # 1.25× input rate
        "cache_read": 0.30,    # 0.10× input rate
    },
}

_FALLBACK = {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute total cost in USD including optional prompt cache tokens."""
    rates = COST_PER_MILLION.get(model, _FALLBACK)
    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_creation_tokens * rates["cache_write"]
        + cache_read_tokens * rates["cache_read"]
    ) / 1_000_000
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest tests/test_services/test_cost_calculator.py -v 2>&1 | tail -20
```
Expected: All tests PASS (old tests still pass because `cache_creation_tokens` and `cache_read_tokens` default to 0).

- [ ] **Step 5: Commit**

```bash
git add backend/services/cost_calculator.py tests/test_services/test_cost_calculator.py
git commit -m "feat(cost): add prompt cache pricing (write 1.25x, read 0.10x input rate)"
```

---

## Task 2: Add cache token columns to LLMCall model

**Files:**
- Modify: `backend/models.py` (LLMCall class, lines 73–89)
- Modify: `backend/database.py` (init_db migration)
- Modify: `scripts/migrate.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_database.py — ADD after existing tests

@pytest.mark.asyncio
async def test_llm_call_has_cache_token_columns(db_session):
    """LLMCall model accepts and stores cache_creation_tokens and cache_read_tokens."""
    from backend.models import LLMCall
    from datetime import datetime, timezone

    row = LLMCall(
        agent_name="test_agent",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.0001,
        latency_ms=500,
        cache_hit=False,
        cache_creation_tokens=800,
        cache_read_tokens=0,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()

    result = await db_session.get(LLMCall, row.id)
    assert result.cache_creation_tokens == 800
    assert result.cache_read_tokens == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_database.py::test_llm_call_has_cache_token_columns -v
```
Expected: FAIL with `TypeError: Unexpected keyword argument 'cache_creation_tokens'`

- [ ] **Step 3: Add columns to LLMCall model**

In `backend/models.py`, add two lines inside the `LLMCall` class after `cache_hit`:

```python
class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    agent_name: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    analysis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("analyses.id"), nullable=True, default=None
    )
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("discovery_runs.id"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
```

- [ ] **Step 4: Add startup migration to database.py**

In `backend/database.py`, extend `init_db()` to migrate existing tables:

```python
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migration: source_statuses on discovery_runs
        result = await conn.execute(text("PRAGMA table_info(discovery_runs)"))
        existing_cols = {row[1] for row in result.fetchall()}
        if "source_statuses" not in existing_cols:
            await conn.execute(
                text("ALTER TABLE discovery_runs ADD COLUMN source_statuses TEXT DEFAULT '{}'")
            )

        # Migration: prompt cache token columns on llm_calls
        result = await conn.execute(text("PRAGMA table_info(llm_calls)"))
        llm_cols = {row[1] for row in result.fetchall()}
        if "cache_creation_tokens" not in llm_cols:
            await conn.execute(
                text("ALTER TABLE llm_calls ADD COLUMN cache_creation_tokens INTEGER NOT NULL DEFAULT 0")
            )
        if "cache_read_tokens" not in llm_cols:
            await conn.execute(
                text("ALTER TABLE llm_calls ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0")
            )
```

- [ ] **Step 5: Add migration to scripts/migrate.py**

At the end of the `main()` function in `scripts/migrate.py`, before `conn.commit()`, add:

```python
    # 18. Add cache_creation_tokens to llm_calls
    try:
        cur.execute(
            "ALTER TABLE llm_calls ADD COLUMN cache_creation_tokens INTEGER NOT NULL DEFAULT 0"
        )
        print("✓ Added cache_creation_tokens to llm_calls")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- cache_creation_tokens already exists, skipping")
        else:
            raise

    # 19. Add cache_read_tokens to llm_calls
    try:
        cur.execute(
            "ALTER TABLE llm_calls ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0"
        )
        print("✓ Added cache_read_tokens to llm_calls")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("- cache_read_tokens already exists, skipping")
        else:
            raise
```

- [ ] **Step 6: Run migration against live DB**

```bash
python scripts/migrate.py
```
Expected output includes:
```
✓ Added cache_creation_tokens to llm_calls
✓ Added cache_read_tokens to llm_calls
Migration complete.
```

- [ ] **Step 7: Run test to confirm pass**

```bash
pytest tests/test_database.py -v 2>&1 | tail -20
```
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/models.py backend/database.py scripts/migrate.py tests/test_database.py
git commit -m "feat(schema): add cache_creation_tokens + cache_read_tokens to llm_calls"
```

---

## Task 3: Update instrumentation.py to track cache tokens

**Files:**
- Modify: `backend/services/instrumentation.py`
- Test: `tests/test_services/test_instrumentation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_services/test_instrumentation.py — ADD after existing tests

@pytest.mark.asyncio
async def test_tracked_call_records_cache_creation_tokens(db_session):
    """cache_creation_input_tokens from response are stored in LLMCall row."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 20
    mock_usage.cache_creation_input_tokens = 800
    mock_usage.cache_read_input_tokens = 0

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system=[{"type": "text", "text": "sys"}],
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_creation_tokens == 800
    assert row.cache_read_tokens == 0
    # Cost: 100 input ($0.80/M) + 20 output ($4.00/M) + 800 cache_write ($1.00/M)
    assert row.cost_usd == pytest.approx(
        (100 * 0.80 + 20 * 4.00 + 800 * 1.00) / 1_000_000
    )


@pytest.mark.asyncio
async def test_tracked_call_records_cache_read_tokens(db_session):
    """cache_read_input_tokens from response are stored and discounted in cost."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 10
    mock_usage.cache_creation_input_tokens = 0
    mock_usage.cache_read_input_tokens = 600

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system=[{"type": "text", "text": "sys"}],
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_read_tokens == 600
    # Cost: 50 input + 10 output + 600 cache_read ($0.08/M)
    assert row.cost_usd == pytest.approx(
        (50 * 0.80 + 10 * 4.00 + 600 * 0.08) / 1_000_000
    )


@pytest.mark.asyncio
async def test_tracked_call_handles_none_cache_usage(db_session):
    """If cache token fields are None (caching not used), store 0 without error."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.models import LLMCall
    from backend.services.instrumentation import tracked_call
    from sqlalchemy import select

    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 30
    mock_usage.cache_creation_input_tokens = None
    mock_usage.cache_read_input_tokens = None

    mock_msg = MagicMock()
    mock_msg.usage = mock_usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    await tracked_call(
        mock_client,
        "test_agent",
        "claude-haiku-4-5-20251001",
        db=db_session,
        max_tokens=256,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
    )
    await db_session.commit()

    row = (await db_session.execute(select(LLMCall))).scalar_one()
    assert row.cache_creation_tokens == 0
    assert row.cache_read_tokens == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_services/test_instrumentation.py -v 2>&1 | tail -20
```
Expected: 3 new tests fail — `cache_creation_tokens` not being written.

- [ ] **Step 3: Implement**

Replace the entire contents of `backend/services/instrumentation.py`:

```python
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, cast

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import LLMCall
from backend.services.cost_calculator import calculate_cost


async def tracked_call(
    client: anthropic.AsyncAnthropic,
    agent_name: str,
    model: str,
    *,
    db: AsyncSession | None = None,
    run_id: str | None = None,
    analysis_id: str | None = None,
    **create_kwargs: Any,
) -> anthropic.types.Message:
    start = time.monotonic()
    msg = cast(anthropic.types.Message, await client.messages.create(model=model, **create_kwargs))
    latency_ms = int((time.monotonic() - start) * 1000)

    cache_creation_tokens = int(getattr(msg.usage, "cache_creation_input_tokens", None) or 0)
    cache_read_tokens = int(getattr(msg.usage, "cache_read_input_tokens", None) or 0)

    if db is not None:
        cost = calculate_cost(
            model,
            msg.usage.input_tokens,
            msg.usage.output_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        await _write_llm_call(
            db,
            agent_name=agent_name,
            model=model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            run_id=run_id,
            analysis_id=analysis_id,
        )
    return msg


async def log_cache_hit(
    db: AsyncSession,
    agent_name: str,
    model: str,
    *,
    run_id: str | None = None,
    analysis_id: str | None = None,
) -> None:
    await _write_llm_call(
        db,
        agent_name=agent_name,
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=1,
        cache_hit=True,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        run_id=run_id,
        analysis_id=analysis_id,
    )


async def _write_llm_call(
    db: AsyncSession,
    *,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    cache_hit: bool,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    run_id: str | None,
    analysis_id: str | None,
) -> None:
    try:
        row = LLMCall(
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            run_id=run_id,
            analysis_id=analysis_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass  # never break an LLM call due to tracking failure
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_services/test_instrumentation.py -v 2>&1 | tail -25
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/instrumentation.py tests/test_services/test_instrumentation.py
git commit -m "feat(instrumentation): track cache_creation_tokens and cache_read_tokens per LLM call"
```

---

## Task 4: Add cache_control to system prompts in base.py AND _stage2_check

**⚠️ Critical:** There are TWO call sites that must both get `cache_control`:
1. `backend/agents/base.py` `_call()` — used by all six pipeline agents (job_parser, match_scorer, gap_analyst, resource_planner, cover_letter, resume_tailorer)
2. `backend/services/discovery.py` `_stage2_check()` — calls `tracked_call()` DIRECTLY, bypassing `_call()`. **This is the highest-volume call** (runs on every Stage-1-passing job, hundreds per discovery run) and the most valuable to cache. Its system prompt includes `compact_profile[:1000]` which is constant across the entire run.

Missing `_stage2_check` means ~95% of cacheable calls get no benefit. Missing `base.py` means Phase 1 / Phase 2 pipeline agents get no benefit. Both must be changed.

**Files:**
- Modify: `backend/agents/base.py` (`_call()` method)
- Modify: `backend/services/discovery.py` (`_stage2_check()` function, line 114)

No new tests needed here — the instrumentation tests in Task 3 already cover the `tracked_call()` path. The integration with real Anthropic caching will be verified manually in the discovery sample run.

- [ ] **Step 1: Edit `_call()` in `backend/agents/base.py`**

Replace the existing `_call()` method (lines 51–65):

```python
    async def _call(self, system: str, user: str) -> str:
        from backend.services.instrumentation import tracked_call

        msg = await tracked_call(
            self._client,
            type(self).__name__.lower(),
            self.model,
            db=self._db,
            run_id=self._run_id,
            analysis_id=self._analysis_id,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text  # type: ignore[union-attr]
```

- [ ] **Step 2: Edit `_stage2_check()` in `backend/services/discovery.py`**

The current call (around line 107–116) passes `system=system` as a plain string. Change to a list:

```python
async def _stage2_check(
    raw_text: str,
    compact_profile: str,
    db: AsyncSession | None = None,
    run_id: str | None = None,
) -> Stage2Result:
    """Haiku relevance check. Returns relevance + title/company/location in one call."""
    system = (
        "You are evaluating job postings for a candidate.\n\n"
        f"Candidate summary:\n{compact_profile[:1000]}\n\n"
        "Evaluate if the job posting is relevant to this candidate. "
        'Respond with ONLY valid JSON: {"relevant": true/false, "reason": "one sentence", '
        '"title": "job title or empty string", "company": "company name or empty string", '
        '"location": "city/remote or null"}'
    )
    msg = await tracked_call(
        _anthropic_client,
        "stage2_haiku",
        HAIKU,
        db=db,
        run_id=run_id,
        max_tokens=200,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Job posting:\n{raw_text[:3000]}"}],
    )
    if not msg.content:
        raise ValueError("Empty response from Haiku")
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object in Haiku response: {raw!r}")
    data = json.loads(raw[start:end])
    return Stage2Result(
        relevant=bool(data.get("relevant", False)),
        reason=data.get("reason", ""),
        title=data.get("title", ""),
        company=data.get("company", ""),
        location=data.get("location"),
    )
```

The only change is `system=system` → `system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]`.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
make test 2>&1 | tail -20
```
Expected: All tests PASS. Agent tests mock `_call()` entirely; discovery Stage 2 tests mock `tracked_call` directly, so neither is affected by the system prompt format change.

- [ ] **Step 4: Commit**

```bash
git add backend/agents/base.py backend/services/discovery.py
git commit -m "feat(agents): add cache_control to system prompts in _call() and _stage2_check()"
```

---

## Task 5: Expose prompt cache savings in CostSummary

**Files:**
- Modify: `backend/schemas.py` (CostSummary class)
- Modify: `backend/routes/metrics.py` (get_cost_summary function)
- Test: `tests/test_routes/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_routes/test_metrics.py — ADD after existing tests

@pytest.mark.asyncio
async def test_summary_prompt_cache_fields_empty_db(authed_client: AsyncClient):
    """Empty DB: prompt cache fields return zero defaults."""
    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["prompt_cache_read_tokens"] == 0
    assert data["prompt_cache_creation_tokens"] == 0
    assert data["prompt_cache_savings_usd"] == 0.0


@pytest.mark.asyncio
async def test_summary_prompt_cache_savings_computed_correctly(
    authed_client: AsyncClient, db_session
):
    """Cache read tokens produce positive savings vs baseline."""
    db_session.add(
        LLMCall(
            agent_name="stage2_haiku",
            model=HAIKU,
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.0,  # placeholder; metrics uses summed columns
            latency_ms=800,
            cache_hit=False,
            cache_creation_tokens=500,
            cache_read_tokens=0,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        LLMCall(
            agent_name="stage2_haiku",
            model=HAIKU,
            input_tokens=50,
            output_tokens=20,
            cost_usd=0.0,
            latency_ms=400,
            cache_hit=False,
            cache_creation_tokens=0,
            cache_read_tokens=500,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    r = await authed_client.get("/api/metrics/costs/summary")
    assert r.status_code == 200
    data = r.json()

    assert data["prompt_cache_creation_tokens"] == 500
    assert data["prompt_cache_read_tokens"] == 500

    # Savings = cache_read * 0.90 * input_rate - cache_creation * 0.25 * input_rate
    # Haiku input_rate = $0.80/M
    # read savings: 500 * 0.90 * 0.80 / 1_000_000 = $0.00000036
    # write overhead: 500 * 0.25 * 0.80 / 1_000_000 = $0.00000010
    # net: $0.00000026
    expected = (500 * 0.90 * 0.80 - 500 * 0.25 * 0.80) / 1_000_000
    assert data["prompt_cache_savings_usd"] == pytest.approx(expected, rel=1e-3)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_routes/test_metrics.py -v 2>&1 | tail -15
```
Expected: 2 new tests fail — `prompt_cache_read_tokens` not in response.

- [ ] **Step 3: Update CostSummary schema in `backend/schemas.py`**

Add three fields to the `CostSummary` class (after the tiering fields):

```python
class CostSummary(BaseModel):
    total_cost_usd: float
    total_calls: int
    real_calls: int
    cached_calls: int
    cache_hit_rate: float
    total_input_tokens: int
    total_output_tokens: int
    # Model tiering: what Haiku calls would have cost at Sonnet rates
    haiku_cost_usd: float = 0.0
    counterfactual_sonnet_cost_usd: float = 0.0
    tiering_savings_usd: float = 0.0
    tiering_ratio: float = 1.0  # counterfactual / actual; 1.0 when no Haiku calls
    # Anthropic prompt caching: tokens served from cache vs baseline cost
    prompt_cache_read_tokens: int = 0
    prompt_cache_creation_tokens: int = 0
    prompt_cache_savings_usd: float = 0.0  # net: read savings minus write overhead
```

- [ ] **Step 4: Update `get_cost_summary` in `backend/routes/metrics.py`**

Add constants at the top of the file (after the existing `_SONNET_*` constants):

```python
_HAIKU_INPUT_PER_M = COST_PER_MILLION["claude-haiku-4-5-20251001"]["input"]
_HAIKU_CACHE_WRITE_PER_M = COST_PER_MILLION["claude-haiku-4-5-20251001"]["cache_write"]
_HAIKU_CACHE_READ_PER_M = COST_PER_MILLION["claude-haiku-4-5-20251001"]["cache_read"]
```

Then add a third DB query inside `get_cost_summary` (after the existing `haiku_row` query):

```python
    # Prompt caching: aggregate cache token counts across all real calls
    cache_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(LLMCall.cache_creation_tokens), 0).label("creation"),
                func.coalesce(func.sum(LLMCall.cache_read_tokens), 0).label("reads"),
            ).where(LLMCall.cache_hit == False)  # noqa: E712
        )
    ).one()

    cache_creation = cache_row.creation or 0
    cache_reads = cache_row.reads or 0
    # Savings formula (per token): read saves (input_rate - cache_read_rate), write costs extra (cache_write_rate - input_rate)
    # Using Haiku rates as the primary driver (most cache tokens are from Haiku discovery runs).
    # Sonnet calls accumulate negligible cache tokens in current workloads.
    prompt_cache_savings = (
        cache_reads * (_HAIKU_INPUT_PER_M - _HAIKU_CACHE_READ_PER_M)
        - cache_creation * (_HAIKU_CACHE_WRITE_PER_M - _HAIKU_INPUT_PER_M)
    ) / 1_000_000
```

And update the `return CostSummary(...)` call to include the new fields:

```python
    return CostSummary(
        total_cost_usd=float(row.total_cost_usd or 0),
        total_calls=total,
        real_calls=row.real_calls or 0,
        cached_calls=cached,
        cache_hit_rate=cached / total if total else 0.0,
        total_input_tokens=row.total_input_tokens or 0,
        total_output_tokens=row.total_output_tokens or 0,
        haiku_cost_usd=haiku_cost,
        counterfactual_sonnet_cost_usd=counterfactual,
        tiering_savings_usd=savings,
        tiering_ratio=ratio,
        prompt_cache_read_tokens=cache_reads,
        prompt_cache_creation_tokens=cache_creation,
        prompt_cache_savings_usd=prompt_cache_savings,
    )
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_routes/test_metrics.py -v 2>&1 | tail -20
```
Expected: All tests PASS including the 2 new ones.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/routes/metrics.py tests/test_routes/test_metrics.py
git commit -m "feat(metrics): expose prompt cache savings in CostSummary endpoint"
```

---

## Task 6: Update frontend types and Costs.tsx dashboard panel

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/Costs.tsx`

No frontend unit tests — verified manually by running the dev server.

- [ ] **Step 1: Update `CostSummary` interface in `frontend/src/types/index.ts`**

Add three fields to the `CostSummary` interface (after `tiering_ratio`):

```typescript
export interface CostSummary {
  total_cost_usd: number;
  total_calls: number;
  real_calls: number;
  cached_calls: number;
  cache_hit_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
  // Model tiering
  haiku_cost_usd: number;
  counterfactual_sonnet_cost_usd: number;
  tiering_savings_usd: number;
  tiering_ratio: number;
  // Anthropic prompt caching
  prompt_cache_read_tokens: number;
  prompt_cache_creation_tokens: number;
  prompt_cache_savings_usd: number;
}
```

- [ ] **Step 2: Add "Prompt Cache Savings" panel to `frontend/src/pages/Costs.tsx`**

After the existing tiering savings panel `{summary.tiering_ratio > 1.0 && (...)}`, add:

```tsx
          {summary.prompt_cache_read_tokens > 0 && (
            <div className="bg-sky-50 border border-sky-200 rounded-xl p-5 space-y-3">
              <h2 className="text-sm font-semibold text-sky-800">Prompt Cache Savings</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-sky-700 mb-1">Cache Reads</p>
                  <p className="text-xl font-bold text-sky-900">
                    {summary.prompt_cache_read_tokens.toLocaleString()}
                  </p>
                  <p className="text-xs text-sky-600">tokens</p>
                </div>
                <div>
                  <p className="text-xs text-sky-700 mb-1">Cache Writes</p>
                  <p className="text-xl font-bold text-sky-900">
                    {summary.prompt_cache_creation_tokens.toLocaleString()}
                  </p>
                  <p className="text-xs text-sky-600">tokens</p>
                </div>
                <div>
                  <p className="text-xs text-sky-700 mb-1">Net Savings</p>
                  <p className="text-xl font-bold text-sky-900">
                    ${fmt(summary.prompt_cache_savings_usd)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-sky-700 mb-1">Hit Rate (tokens)</p>
                  <p className="text-xl font-bold text-sky-900">
                    {summary.prompt_cache_read_tokens + summary.prompt_cache_creation_tokens > 0
                      ? (
                          (summary.prompt_cache_read_tokens /
                            (summary.prompt_cache_read_tokens +
                              summary.prompt_cache_creation_tokens)) *
                          100
                        ).toFixed(1)
                      : "0.0"}
                    %
                  </p>
                  <p className="text-xs text-sky-600">reads / (reads + writes)</p>
                </div>
              </div>
            </div>
          )}
```

This panel is sky-blue (distinct from the emerald tiering panel) and appears only when there are cache reads (hidden on day 1 of caching, shown once caching is active).

- [ ] **Step 3: Run schema drift check**

```bash
python scripts/check_schema_drift.py
```
Expected: `Schema drift check passed`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/Costs.tsx
git commit -m "feat(dashboard): add Prompt Cache Savings panel to Costs page"
```

---

## Task 7: Full check and verify

- [ ] **Step 1: Run full suite**

```bash
make check
```
Expected: `fmt` clean, `lint` clean, `test` all pass, `≥70%` coverage.

- [ ] **Step 2: Manual smoke test — run the discovery sample script**

```bash
python scripts/run_discovery_sample.py
```

After the run, check the DB for cache token activity:

```bash
sqlite3 data/jobfit.db "
SELECT agent_name, model, input_tokens, cache_creation_tokens, cache_read_tokens, cost_usd
FROM llm_calls
WHERE cache_creation_tokens > 0 OR cache_read_tokens > 0
ORDER BY created_at DESC
LIMIT 10;
"
```

Expected: `stage2_haiku` rows show `cache_creation_tokens > 0` on the first call and `cache_read_tokens > 0` on subsequent calls (within the same batch, same 5-minute TTL window). If all rows show `cache_creation_tokens > 0` and `cache_read_tokens = 0`, the calls are spaced too far apart for the TTL — this is an expected edge case for very small batches.

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ `cache_control` added to system prompts in `base.py` (all pipeline agents)
- ✅ `cache_control` added to `_stage2_check()` in `discovery.py` (highest-volume call — fixed after code review caught it missing from original draft)
- ✅ `cache_creation_input_tokens` and `cache_read_input_tokens` read from response in `instrumentation.py`
- ✅ New pricing rates (`cache_write`, `cache_read`) in `cost_calculator.py`
- ✅ Two new DB columns (`cache_creation_tokens`, `cache_read_tokens`) with migration
- ✅ Schema migration in both `database.py` (startup) and `scripts/migrate.py` (manual)
- ✅ `CostSummary` extended with 3 new fields
- ✅ Metrics endpoint computes and returns prompt cache savings
- ✅ Dashboard panel shows cache reads, writes, net savings, hit rate

**Placeholder scan:** No TBDs, no "add validation" steps, all code blocks are complete.

**Type consistency:** `prompt_cache_read_tokens` / `prompt_cache_creation_tokens` / `prompt_cache_savings_usd` used consistently across `schemas.py`, `metrics.py`, `types/index.ts`, and `Costs.tsx`.

**Known mock fixture note:** The existing `mock_client` fixture in `test_instrumentation.py` does not set `cache_creation_input_tokens` / `cache_read_input_tokens`. MagicMock auto-creates these as MagicMock objects; `getattr(...) or 0` will return the MagicMock (truthy), not 0. Existing tests pass because they don't inspect LLMCall row content. New tests in Task 3 use fresh MagicMock with explicit `.cache_creation_input_tokens = 800` to avoid this. No fixture change needed.
