"""add profile review fields

Revision ID: 0002_profile_review
Revises: 0001_initial
Create Date: 2026-06-09 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_profile_review"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "profile_review_data",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "review_status",
                sa.String(),
                nullable=False,
                server_default="draft",
            )
        )
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.alter_column("profile_review_data", server_default=None)
        batch_op.alter_column("review_status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_status")
        batch_op.drop_column("profile_review_data")
