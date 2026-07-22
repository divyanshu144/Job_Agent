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


def _doc_table(name: str) -> None:
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
    _doc_table("resume_documents")
    _doc_table("cover_letter_documents")
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
    )
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
    op.drop_table("resume_edit_rules")
    op.drop_table("resume_document_revisions")
    op.drop_table("cover_letter_documents")
    op.drop_table("resume_documents")
