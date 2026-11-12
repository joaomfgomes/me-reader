"""Tabela das respostas do tutor guardadas em cache."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UtcDateTime


def _now() -> datetime:
    return datetime.now(UTC)


class TutorResponse(Base):
    """Uma resposta do tutor, já validada.

    Como o áudio, é identificada pelo hash do que a gerou (frase, palavra,
    tipo de pedido, modelo e versão do prompt) e nunca é alterada (ADR-004).
    Não guarda a frase: só a explicação, que é o que custou dinheiro obter.
    """

    __tablename__ = "tutor_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Tipo de pedido. Por agora só "word"; a Fase 4 acrescenta os restantes.
    kind: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[int] = mapped_column(Integer)
    # A explicação, no formato de WordExplanation.
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
