"""add context metadata

Revision ID: 0010_context_metadata
Revises: 0009_password_reset_tokens
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_context_metadata"
down_revision: Union[str, None] = "0009_password_reset_tokens"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "context_chars" not in _columns("llm_calls"):
        op.add_column(
            "llm_calls",
            sa.Column("context_chars", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("llm_calls", "context_chars", server_default=None)
    if "context_json" not in _columns("job_results"):
        op.add_column("job_results", sa.Column("context_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if "context_json" in _columns("job_results"):
        op.drop_column("job_results", "context_json")
    if "context_chars" in _columns("llm_calls"):
        op.drop_column("llm_calls", "context_chars")
