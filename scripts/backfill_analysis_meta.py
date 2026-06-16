"""One-time backfill for the History page (run manually).

Populates the denormalized Analysis.role_type / company / match_score columns from existing
job_results JSON, and optionally claims orphaned pre-auth manual analyses (user_id NULL AND
job_id NULL) by assigning them to a user.

Usage:
    python scripts/backfill_analysis_meta.py                          # backfill meta only
    python scripts/backfill_analysis_meta.py --claim-orphans          # + claim orphans (sole user)
    python scripts/backfill_analysis_meta.py --claim-orphans --email you@example.com

Idempotent: backfill only touches rows with NULL role_type; claim only touches rows with both
user_id and job_id NULL. Safe to re-run. Reports counts.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import SessionLocal
from backend.models import Analysis, JobResult, User


async def _meta_for(
    db: AsyncSession, analysis_id: str
) -> tuple[str | None, str | None, int | None]:
    rows = (
        (await db.execute(select(JobResult).where(JobResult.analysis_id == analysis_id)))
        .scalars()
        .all()
    )
    role_type = company = None
    score: int | None = None
    for r in rows:
        if not r.output_json:
            continue
        data = json.loads(r.output_json)
        if r.agent_name == "job_parser":
            role_type = data.get("role_type")
            company = data.get("company")
        elif r.agent_name == "match_scorer":
            score = data.get("score")
    return role_type, company, score


async def backfill_meta(db: AsyncSession) -> int:
    """Populate role_type/company/match_score for analyses missing them. Returns count updated."""
    analyses = (
        (await db.execute(select(Analysis).where(Analysis.role_type.is_(None)))).scalars().all()
    )
    updated = 0
    for a in analyses:
        role_type, company, score = await _meta_for(db, a.id)
        if role_type is None and company is None and score is None:
            continue
        a.role_type, a.company, a.match_score = role_type, company, score
        updated += 1
    await db.commit()
    return updated


async def claim_orphans(db: AsyncSession, email: str | None = None) -> int:
    """Assign orphaned manual analyses (user_id NULL AND job_id NULL) to a user. Returns count."""
    if email:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user with email {email!r}")
    else:
        users = (await db.execute(select(User))).scalars().all()
        if len(users) != 1:
            raise SystemExit("Pass --email: there is not exactly one user to claim for.")
        user = users[0]
    orphans = (
        (
            await db.execute(
                select(Analysis).where(Analysis.user_id.is_(None), Analysis.job_id.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for a in orphans:
        a.user_id = user.id
    await db.commit()
    print(f"Claimed {len(orphans)} orphaned manual analyses for {user.email}")
    return len(orphans)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claim-orphans", action="store_true", help="assign orphaned manual analyses")
    ap.add_argument("--email", default=None, help="owner email when claiming (default: sole user)")
    args = ap.parse_args()

    async with SessionLocal() as db:
        n = await backfill_meta(db)
        print(f"Backfilled meta on {n} analyses")
        if args.claim_orphans:
            await claim_orphans(db, args.email)


if __name__ == "__main__":
    asyncio.run(main())
