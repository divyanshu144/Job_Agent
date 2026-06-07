"""add campaign_jobs

Revision ID: 0001_add_campaign_jobs
Revises:
Create Date: 2026-06-07

First Alembic revision. Creates the campaign_jobs table (autonomous application
campaign tracking). Hand-authored to match backend.models.CampaignJob.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_add_campaign_jobs"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("draft_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_jobs_job_id", "campaign_jobs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_jobs_job_id", table_name="campaign_jobs")
    op.drop_table("campaign_jobs")
