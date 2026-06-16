#!/usr/bin/env python3
"""Run a capped discovery batch (25 jobs) against the live Anthropic API.

Usage (from repo root):
    python scripts/run_discovery_sample.py

What it does:
1. Fetches the current HN "Who's hiring?" thread
2. Takes only the first 25 jobs (caps cost at ~$0.05)
3. Runs them through the full discovery pipeline:
   - Stage 1: keyword filter (free)
   - Stage 2: Haiku relevance check (~$0.0006/job)
   - Phase 1: Haiku job_parser + match_scorer + gap_analyst on passing jobs
4. Writes all llm_calls to the real jobfit.db
5. Prints the tiering metrics summary
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow import of backend modules from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))


from datetime import datetime, timezone

from sqlalchemy import select, update

from backend.agents.base import HAIKU, SONNET
from backend.database import SessionLocal, init_db
from backend.models import DiscoveryRun, LLMCall
from backend.services.cost_calculator import COST_PER_MILLION
from backend.services.discovery import (
    _DISCOVERY_CONCURRENCY,
    _load_search_profiles,
    _process_job,
)
from backend.services.hn_client import fetch_hn_jobs
from backend.services.profile_builder import build_compact_profile, get_or_build_profile

JOB_CAP = 25  # Keep spend < $0.10


async def main() -> None:
    print("=== JobFit Discovery Sample Run ===\n")

    # 1. Init DB (idempotent)
    await init_db()

    # 2. Fetch HN jobs and cap
    print(f"Fetching HN jobs (will cap at {JOB_CAP})...")
    all_jobs = await fetch_hn_jobs()
    if not all_jobs:
        print("ERROR: No HN jobs returned. Check internet connectivity.")
        return
    raw_jobs = all_jobs[:JOB_CAP]
    print(f"  Found {len(all_jobs)} total jobs on HN thread, using first {len(raw_jobs)}")

    # 3. Create a DiscoveryRun row
    async with SessionLocal() as db:
        run = DiscoveryRun(
            source="hn_sample",
            triggered_by="script",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.commit()
        run_id = run.id
        print(f"  Created discovery run: {run_id}\n")

        profiles = _load_search_profiles()
        profile = await get_or_build_profile(db)
        compact = build_compact_profile(profile.yaml_data, profile.cv_text)

        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(jobs_found=len(raw_jobs))
        )
        await db.commit()

    # 4. Process jobs with the same bounded concurrency as production
    sem = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _bounded(raw):  # type: ignore[no-untyped-def]
        async with sem:
            async with SessionLocal() as db:
                await _process_job(
                    db, run_id, raw, profiles, profile, compact, source_tag="hn"
                )

    print(
        f"Processing {len(raw_jobs)} jobs through pipeline "
        "(Stage 1 → Stage 2 Haiku → Phase 1 Haiku)..."
    )
    results = await asyncio.gather(*[_bounded(raw) for raw in raw_jobs], return_exceptions=True)
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        print(f"  WARNING: {len(errors)} jobs failed with exceptions")
        for e in errors[:3]:
            print(f"    {e}")

    # Mark run complete
    async with SessionLocal() as db:
        await db.execute(
            update(DiscoveryRun)
            .where(DiscoveryRun.id == run_id)
            .values(status="complete", completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
    print("  Pipeline complete.\n")

    # 5. Query metrics
    async with SessionLocal() as db:
        # Run funnel
        run_row = (
            await db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id))
        ).scalar_one()

        # All llm_calls for this run
        calls = (
            await db.execute(
                select(LLMCall)
                .where(LLMCall.run_id == run_id)
                .order_by(LLMCall.created_at)
            )
        ).scalars().all()

        # First 5 rows for raw inspection
        first5 = calls[:5]

        # Tiering computation
        haiku_calls = [c for c in calls if c.model == HAIKU and not c.cache_hit]
        haiku_input = sum(c.input_tokens for c in haiku_calls)
        haiku_output = sum(c.output_tokens for c in haiku_calls)
        haiku_cost = sum(c.cost_usd for c in haiku_calls)

        sonnet_input_rate = COST_PER_MILLION[SONNET]["input"]
        sonnet_output_rate = COST_PER_MILLION[SONNET]["output"]
        counterfactual = (
            haiku_input * sonnet_input_rate + haiku_output * sonnet_output_rate
        ) / 1_000_000
        savings = counterfactual - haiku_cost
        ratio = counterfactual / haiku_cost if haiku_cost > 0 else 1.0

        total_cost = sum(c.cost_usd for c in calls if not c.cache_hit)
        cached = sum(1 for c in calls if c.cache_hit)

    print("=== Discovery Funnel ===")
    print(f"  Jobs found:          {run_row.jobs_found}")
    print(f"  Passed Stage 1:      {run_row.jobs_passed_stage1}")
    print(f"  Passed Stage 2:      {run_row.jobs_passed_stage2}")
    print(f"  Scored (Phase 1):    {run_row.jobs_scored}")
    print()

    print("=== LLM Call Stats ===")
    print(f"  Total calls:         {len(calls)}")
    print(f"  Real calls:          {len(calls) - cached}")
    print(f"  Cached calls:        {cached}")
    print(f"  Total cost (actual): ${total_cost:.6f}")
    print()

    print("=== Tiering Metrics ===")
    print(f"  haiku_cost_usd:               ${haiku_cost:.6f}")
    print(f"  counterfactual_sonnet_cost:   ${counterfactual:.6f}")
    print(f"  tiering_savings_usd:          ${savings:.6f}")
    print(f"  tiering_ratio:                {ratio:.4f}×")
    print()

    print("=== First 5 llm_calls rows ===")
    print(
        f"{'agent_name':<25} {'model':<30} {'input_tok':>9} "
        f"{'out_tok':>7} {'cost_usd':>10} {'cached':>6}"
    )
    print("-" * 90)
    for c in first5:
        model_short = (
            c.model.replace("claude-", "")
            .replace("-4-5-20251001", "-haiku")
            .replace("sonnet-4-6", "sonnet")
        )
        print(
            f"{c.agent_name:<25} {model_short:<30} {c.input_tokens:>9} {c.output_tokens:>7} "
            f"${c.cost_usd:>9.6f} {'YES' if c.cache_hit else 'no':>6}"
        )

    print()
    expected_ratio = (
        COST_PER_MILLION[SONNET]["input"] / COST_PER_MILLION[HAIKU]["input"]
    )  # ~3.75
    if ratio >= expected_ratio * 0.8:
        print(f"✓ tiering_ratio {ratio:.2f}× is within 20% of expected {expected_ratio:.2f}×")
    elif haiku_cost == 0:
        print("⚠ No Haiku calls recorded — all jobs may have been deduped or Stage 1 filtered all.")
    else:
        print(
            f"⚠ tiering_ratio {ratio:.2f}× is below expected "
            f"{expected_ratio:.2f}× — investigate token counts."
        )

    print(f"\nRun ID: {run_id}")
    print("Done. Check /costs in the frontend for the emerald panel.")


if __name__ == "__main__":
    asyncio.run(main())
