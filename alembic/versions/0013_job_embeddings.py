"""add job embeddings for semantic discovery

Revision ID: 0013_job_embeddings
Revises: 0012_pgvector_embeddings
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013_job_embeddings"
down_revision: Union[str, None] = "0012_pgvector_embeddings"
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
    existing = _columns("jobs")
    if "embedding_model" not in existing:
        op.add_column("jobs", sa.Column("embedding_model", sa.String(), nullable=True))
    if "embedding_json" not in existing:
        op.add_column("jobs", sa.Column("embedding_json", sa.Text(), nullable=True))

    if _vector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if _has_vector_extension() and "embedding_vector" not in existing:
        op.execute("ALTER TABLE jobs ADD COLUMN embedding_vector vector(1536)")


def downgrade() -> None:
    existing = _columns("jobs")
    if _has_vector_extension() and "embedding_vector" in existing:
        op.execute("ALTER TABLE jobs DROP COLUMN embedding_vector")
    if "embedding_json" in existing:
        op.drop_column("jobs", "embedding_json")
    if "embedding_model" in existing:
        op.drop_column("jobs", "embedding_model")
