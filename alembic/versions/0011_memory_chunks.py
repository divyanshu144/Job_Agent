"""add memory chunks

Revision ID: 0011_memory_chunks
Revises: 0010_context_metadata
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011_memory_chunks"
down_revision: Union[str, None] = "0010_context_metadata"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "memory_chunks" in existing_tables:
        return
    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("sparse_vector_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_chunks_user_id", "memory_chunks", ["user_id"], unique=False)
    op.create_index("ix_memory_chunks_profile_id", "memory_chunks", ["profile_id"], unique=False)
    op.create_index(
        "ix_memory_chunks_profile_namespace",
        "memory_chunks",
        ["profile_id", "namespace"],
        unique=False,
    )


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "memory_chunks" not in existing_tables:
        return
    op.drop_index("ix_memory_chunks_profile_namespace", table_name="memory_chunks")
    op.drop_index("ix_memory_chunks_profile_id", table_name="memory_chunks")
    op.drop_index("ix_memory_chunks_user_id", table_name="memory_chunks")
    op.drop_table("memory_chunks")
