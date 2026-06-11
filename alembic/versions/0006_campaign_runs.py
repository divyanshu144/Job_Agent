"""campaign runs ledger

Revision ID: 0006_campaign_runs
Revises: 0005_user_targets
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_campaign_runs"
down_revision: Union[str, None] = "0005_user_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("jobs_considered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_drafted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_runs_user_id", "campaign_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_runs_user_id", table_name="campaign_runs")
    op.drop_table("campaign_runs")
