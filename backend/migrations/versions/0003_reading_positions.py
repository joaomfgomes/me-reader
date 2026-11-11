"""Tabela reading_positions: a frase onde o leitor parou em cada documento.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_positions",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("sentence_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_reading_positions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sentence_id"],
            ["sentences.id"],
            name=op.f("fk_reading_positions_sentence_id_sentences"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_reading_positions")),
    )


def downgrade() -> None:
    op.drop_table("reading_positions")
