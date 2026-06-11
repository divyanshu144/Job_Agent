"""per-user target companies

Revision ID: 0005_user_targets
Revises: 0004_user_caps
Create Date: 2026-06-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_user_targets"
down_revision: Union[str, None] = "0004_user_caps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_target_companies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ats", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ats", "slug", name="uq_user_target"),
    )
    op.create_index(
        "ix_user_target_companies_user_id", "user_target_companies", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_target_companies_user_id", table_name="user_target_companies")
    op.drop_table("user_target_companies")
