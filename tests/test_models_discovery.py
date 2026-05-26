from __future__ import annotations

import backend.models  # noqa: F401
from backend.database import Base


async def test_new_tables_registered():
    """DiscoveryRun and Job tables exist in metadata."""
    table_names = set(Base.metadata.tables.keys())
    assert "discovery_runs" in table_names
    assert "jobs" in table_names


async def test_analysis_has_job_id_column():
    """Analysis table has job_id column."""
    cols = {c.name for c in Base.metadata.tables["analyses"].columns}
    assert "job_id" in cols


async def test_job_has_globally_unique_dedup_hash():
    """jobs.dedup_hash has a unique constraint."""
    table = Base.metadata.tables["jobs"]
    job_cols_with_unique = {c.name for c in table.columns if getattr(c, "unique", False)}
    assert "dedup_hash" in job_cols_with_unique
