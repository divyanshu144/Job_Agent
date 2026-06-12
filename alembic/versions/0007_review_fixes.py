"""code-review fixes: llm_calls spend index + one-running-campaign-run guard

Revision ID: 0007_review_fixes
Revises: 0006_campaign_runs
Create Date: 2026-06-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_review_fixes"
down_revision: Union[str, None] = "0006_campaign_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_spend() sums cost per user per window on every campaign cap check;
    # llm_calls is the fastest-growing table — without this it's a full scan.
    op.create_index("ix_llm_calls_user_created", "llm_calls", ["user_id", "created_at"])

    # One-time cleanup so the partial unique index below can be created: keep
    # only the newest 'running' row per user, fail the rest (zombies from
    # killed workers / lost queue messages).
    op.execute(
        """
        UPDATE campaign_runs SET status = 'failed',
               error = 'run was interrupted (cleanup before unique-running guard)'
        WHERE status = 'running' AND id NOT IN (
            SELECT DISTINCT ON (user_id) id FROM campaign_runs
            WHERE status = 'running' ORDER BY user_id, started_at DESC
        )
        """
    )
    # DB-enforced concurrency guard: at most one running campaign run per user.
    op.create_index(
        "uq_campaign_runs_one_running",
        "campaign_runs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_campaign_runs_one_running", table_name="campaign_runs")
    op.drop_index("ix_llm_calls_user_created", table_name="llm_calls")
