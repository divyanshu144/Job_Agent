"""add prompt version metadata to llm_calls

Revision ID: 0008_llm_call_prompt_versions
Revises: 0007_review_fixes
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_llm_call_prompt_versions"
down_revision: Union[str, None] = "0007_review_fixes"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("llm_calls")}
    with op.batch_alter_table("llm_calls") as batch_op:
        if "prompt_name" not in existing:
            batch_op.add_column(sa.Column("prompt_name", sa.String(), nullable=True))
        if "prompt_hash" not in existing:
            batch_op.add_column(sa.Column("prompt_hash", sa.String(), nullable=True))
        if "prompt_version" not in existing:
            batch_op.add_column(sa.Column("prompt_version", sa.String(), nullable=True))


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("llm_calls")}
    with op.batch_alter_table("llm_calls") as batch_op:
        if "prompt_version" in existing:
            batch_op.drop_column("prompt_version")
        if "prompt_hash" in existing:
            batch_op.drop_column("prompt_hash")
        if "prompt_name" in existing:
            batch_op.drop_column("prompt_name")
