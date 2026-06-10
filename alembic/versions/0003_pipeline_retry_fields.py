"""pipeline retry fields

Revision ID: 0003_pipeline_retry
Revises: 0002_profile_review
Create Date: 2026-06-10 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_pipeline_retry"
down_revision: Union[str, None] = "0002_profile_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # job_results: error_code + retry_count
    with op.batch_alter_table("job_results", schema=None) as batch_op:
        batch_op.add_column(sa.Column("error_code", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
    with op.batch_alter_table("job_results", schema=None) as batch_op:
        batch_op.alter_column("retry_count", server_default=None)

    # analyses: retry_running_at (timestamptz)
    with op.batch_alter_table("analyses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("retry_running_at", sa.DateTime(timezone=True), nullable=True)
        )

    # One-time dedup to satisfy the one-row-per-(analysis, agent) invariant.
    # Keep the output_json row if one exists, else keep one error row; delete the
    # rest. Safe no-op when there are no duplicates.
    op.execute(
        """
        DELETE FROM job_results jr
        USING (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY analysis_id, agent_name
                       ORDER BY (output_json IS NOT NULL) DESC, id DESC
                   ) AS rn
            FROM job_results
        ) ranked
        WHERE jr.id = ranked.id AND ranked.rn > 1
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("analyses", schema=None) as batch_op:
        batch_op.drop_column("retry_running_at")
    with op.batch_alter_table("job_results", schema=None) as batch_op:
        batch_op.drop_column("retry_count")
        batch_op.drop_column("error_code")
