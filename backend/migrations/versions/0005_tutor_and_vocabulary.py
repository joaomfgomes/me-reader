"""Tabelas do tutor (tutor_responses) e do vocabulário, e tokens em usage_events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutor_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tutor_responses")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_tutor_responses_content_hash")),
    )
    op.create_table(
        "vocabulary_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("lemma_key", sa.String(length=200), nullable=False),
        sa.Column("word", sa.String(length=200), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("sentence_text", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("sentence_id", sa.Integer(), nullable=True),
        sa.Column("lookup_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_vocabulary_entries_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sentence_id"],
            ["sentences.id"],
            name=op.f("fk_vocabulary_entries_sentence_id_sentences"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vocabulary_entries")),
        sa.UniqueConstraint("language", "lemma_key", name=op.f("uq_vocabulary_entries_language")),
    )
    with op.batch_alter_table("usage_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usage_events", schema=None) as batch_op:
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")

    op.drop_table("vocabulary_entries")
    op.drop_table("tutor_responses")
