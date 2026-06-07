# tests/test_migrations.py
"""Proves the Alembic env + revisions actually apply against a scratch DB."""

from __future__ import annotations

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_upgrade_head_creates_campaign_jobs(tmp_path):
    db = tmp_path / "scratch.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    try:
        insp = inspect(engine)
        assert "campaign_jobs" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("campaign_jobs")}
        assert {
            "id",
            "job_id",
            "run_at",
            "match_score",
            "draft_id",
            "status",
            "error",
        } <= cols
    finally:
        engine.dispose()
