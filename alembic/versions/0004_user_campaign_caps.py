"""user campaign caps + llm_calls.user_id

Revision ID: 0004_user_caps
Revises: 0003_pipeline_retry
Create Date: 2026-06-10 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_user_caps"
down_revision: Union[str, None] = "0003_pipeline_retry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-user cost attribution on LLM calls (nullable; legacy rows stay null).
    op.add_column("llm_calls", sa.Column("user_id", sa.String(), nullable=True))
    op.create_foreign_key("fk_llm_calls_user_id", "llm_calls", "users", ["user_id"], ["id"])

    op.create_table(
        "user_campaign_settings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("daily_run_cap", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "monthly_cost_cap_usd", sa.Float(), nullable=False, server_default="10.0"
        ),
        sa.Column(
            "campaign_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_user_campaign_settings_user_id", "user_campaign_settings", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_campaign_settings_user_id", table_name="user_campaign_settings")
    op.drop_table("user_campaign_settings")
    op.drop_constraint("fk_llm_calls_user_id", "llm_calls", type_="foreignkey")
    op.drop_column("llm_calls", "user_id")
