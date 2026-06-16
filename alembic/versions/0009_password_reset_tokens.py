"""add password reset tokens

Revision ID: 0009_password_reset_tokens
Revises: 0008_llm_call_prompt_versions
Create Date: 2026-06-16
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_password_reset_tokens"
down_revision: Union[str, None] = "0008_llm_call_prompt_versions"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "password_reset_tokens" in existing_tables:
        return
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_reset_tokens_token",
        "password_reset_tokens",
        ["token"],
        unique=True,
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "password_reset_tokens" not in existing_tables:
        return
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
