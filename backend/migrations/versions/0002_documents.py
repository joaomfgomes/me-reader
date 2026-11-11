"""Tabelas do documento importado: documents, chapters, blocks e sentences.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Gerada com "alembic revision --autogenerate" a partir dos modelos em
    # app/importing/models.py e depois revista à mão. A ordem importa: cada
    # tabela tem de existir antes das que apontam para ela.
    # op.f(...) marca um nome como definitivo, já calculado pela convenção de
    # nomes definida em app/core/db.py.
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("cleaning_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("file_hash", name=op.f("uq_documents_file_hash")),
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chapters_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chapters")),
        sa.UniqueConstraint("document_id", "position", name=op.f("uq_chapters_document_id")),
    )
    op.create_table(
        "blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapters.id"],
            name=op.f("fk_blocks_chapter_id_chapters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocks")),
        sa.UniqueConstraint("chapter_id", "position", name=op.f("uq_blocks_chapter_id")),
    )
    op.create_table(
        "sentences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("words", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["blocks.id"],
            name=op.f("fk_sentences_block_id_blocks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sentences")),
        sa.UniqueConstraint("block_id", "position", name=op.f("uq_sentences_block_id")),
    )


def downgrade() -> None:
    # Pela ordem inversa: primeiro as tabelas que dependem das outras.
    op.drop_table("sentences")
    op.drop_table("blocks")
    op.drop_table("chapters")
    op.drop_table("documents")
