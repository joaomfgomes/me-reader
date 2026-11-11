"""Tabela de registo de consumo."""

from datetime import UTC, datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UtcDateTime


def _now() -> datetime:
    return datetime.now(UTC)


class UsageEvent(Base):
    """Um pedido a um serviço pago, ou que teria sido pago se não houvesse cache.

    Guarda só contagens e identificadores, nunca texto.
    """

    __tablename__ = "usage_events"
    # As consultas são sempre "eventos deste tipo desde o início do mês";
    # este índice responde-lhes sem percorrer a tabela toda.
    __table_args__ = (Index("ix_usage_events_kind_created_at", "kind", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # "tts" (texto para voz). O tutor acrescentará "llm" na Fase 3.
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(50))
    # SET NULL: apagar um documento não apaga o registo do que ele custou.
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    characters: Mapped[int] = mapped_column(Integer)
    # True quando o áudio veio da cache e nada foi pedido ao fornecedor.
    cache_hit: Mapped[bool] = mapped_column()
    # Estimativa, calculada com o preço configurado. Não é uma fatura.
    estimated_cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
