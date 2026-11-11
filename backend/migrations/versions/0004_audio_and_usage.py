"""Tabelas de áudio (audio_assets, block_audio) e de consumo (usage_events).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("voice", sa.String(length=100), nullable=False),
        sa.Column("media_type", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_assets")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_audio_assets_content_hash")),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("characters", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_usage_events_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
    )
    with op.batch_alter_table("usage_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_usage_events_kind_created_at", ["kind", "created_at"], unique=False
        )

    op.create_table(
        "block_audio",
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.Column("audio_asset_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audio_asset_id"],
            ["audio_assets.id"],
            name=op.f("fk_block_audio_audio_asset_id_audio_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["blocks.id"],
            name=op.f("fk_block_audio_block_id_blocks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("block_id", "audio_asset_id", name=op.f("pk_block_audio")),
    )


def downgrade() -> None:
    op.drop_table("block_audio")
    with op.batch_alter_table("usage_events", schema=None) as batch_op:
        batch_op.drop_index("ix_usage_events_kind_created_at")

    op.drop_table("usage_events")
    op.drop_table("audio_assets")
