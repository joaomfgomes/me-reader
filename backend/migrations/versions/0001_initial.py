"""Migração inicial: tabela app_meta.

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Cada migração tem um identificador e aponta para a anterior, formando uma
# cadeia. O Alembic guarda na tabela alembic_version em que elo a base de
# dados está, e é isso que o /health compara com a última migração do código.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A migração repete a definição da tabela em vez de importar o modelo de
    # app/core/db.py. É intencional: uma migração é um registo histórico e tem
    # de continuar a fazer o mesmo, mesmo que o modelo mude no futuro.
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    # A arquitetura prevê migrações sempre para a frente; o downgrade existe
    # para desfazer um engano durante o desenvolvimento.
    op.drop_table("app_meta")
