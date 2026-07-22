"""resume editor: documents, versions, revisions, edit rules

Revision ID: 0014_resume_documents
Revises: 0013_job_embeddings
Create Date: 2026-07-22
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014_resume_documents"
down_revision: Union[str, None] = "0013_job_embeddings"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _doc_table(name: str, existing_tables: set[str]) -> None:
    # Guard against a "legacy full schema" boot (Base.metadata.create_all already
    # ran, e.g. test_startup.py's index-less-legacy-schema simulation): this
    # migration must be a no-op for tables ORM already created, same convention
    # as 0011_memory_chunks.py.
    if name in existing_tables:
        return
    op.create_table(
        name,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), index=True),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analyses.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default="Default"),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rev", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(f"ix_{name}_analysis_id", name, ["analysis_id"])


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    _doc_table("resume_documents", existing_tables)
    _doc_table("cover_letter_documents", existing_tables)
    if "resume_document_revisions" not in existing_tables:
        op.create_table(
            "resume_document_revisions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("document_id", sa.String(), nullable=False, index=True),
            sa.Column("doc_kind", sa.String(), nullable=False),
            sa.Column("rev", sa.Integer(), nullable=False),
            sa.Column("content_json", sa.Text(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("document_id", "rev", name="uq_resume_revision_doc_rev"),
        )
    if "resume_edit_rules" not in existing_tables:
        op.create_table(
            "resume_edit_rules",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), index=True),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("scope", sa.String(), nullable=False, server_default="resume"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "resume_edit_rules" in existing_tables:
        op.drop_table("resume_edit_rules")
    if "resume_document_revisions" in existing_tables:
        op.drop_table("resume_document_revisions")
    if "cover_letter_documents" in existing_tables:
        op.drop_table("cover_letter_documents")
    if "resume_documents" in existing_tables:
        op.drop_table("resume_documents")
