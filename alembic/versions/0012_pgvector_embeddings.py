"""add pgvector semantic embeddings

Revision ID: 0012_pgvector_embeddings
Revises: 0011_memory_chunks
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012_pgvector_embeddings"
down_revision: Union[str, None] = "0011_memory_chunks"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _has_vector_extension() -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("select exists(select 1 from pg_extension where extname = 'vector')"))
        .scalar()
    )


def _vector_available() -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("select exists(select 1 from pg_available_extensions where name = 'vector')"))
        .scalar()
    )


def upgrade() -> None:
    existing = _columns("memory_chunks")
    if "embedding_model" not in existing:
        op.add_column("memory_chunks", sa.Column("embedding_model", sa.String(), nullable=True))
    if "embedding_json" not in existing:
        op.add_column("memory_chunks", sa.Column("embedding_json", sa.Text(), nullable=True))

    if _vector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if _has_vector_extension() and "embedding_vector" not in existing:
        op.execute("ALTER TABLE memory_chunks ADD COLUMN embedding_vector vector(1536)")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_memory_chunks_embedding_vector
            ON memory_chunks
            USING ivfflat (embedding_vector vector_cosine_ops)
            WITH (lists = 100)
            """
        )


def downgrade() -> None:
    existing = _columns("memory_chunks")
    if _has_vector_extension() and "embedding_vector" in existing:
        op.execute("DROP INDEX IF EXISTS ix_memory_chunks_embedding_vector")
        op.execute("ALTER TABLE memory_chunks DROP COLUMN embedding_vector")
    if "embedding_json" in existing:
        op.drop_column("memory_chunks", "embedding_json")
    if "embedding_model" in existing:
        op.drop_column("memory_chunks", "embedding_model")
