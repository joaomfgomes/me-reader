"""Tabela do vocabulário: as palavras que o leitor consultou."""

from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UtcDateTime


def _now() -> datetime:
    return datetime.now(UTC)


class VocabularyEntry(Base):
    """Uma palavra consultada, com a frase onde foi encontrada.

    Há uma entrada por língua e por lema: consultar "went" e depois "going"
    reforça a mesma entrada ("go") em vez de criar duas.
    """

    __tablename__ = "vocabulary_entries"
    __table_args__ = (UniqueConstraint("language", "lemma_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(8))
    # O lema em minúsculas, só para comparar: "Haus" e "haus" são a mesma entrada.
    lemma_key: Mapped[str] = mapped_column(String(200))
    # A palavra tal como apareceu no texto, da primeira vez.
    word: Mapped[str] = mapped_column(String(200))
    # Cópia da explicação (formato de WordExplanation). É uma cópia e não uma
    # ligação à cache para o vocabulário sobreviver a mudanças de modelo ou de
    # prompt.
    explanation: Mapped[dict] = mapped_column(JSON)
    # Cópia da frase original, para o vocabulário se manter mesmo que o
    # documento seja apagado (por isso as ligações abaixo são SET NULL).
    sentence_text: Mapped[str] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    sentence_id: Mapped[int | None] = mapped_column(ForeignKey("sentences.id", ondelete="SET NULL"))
    # Quantas vezes a palavra foi consultada: as mais consultadas são as que
    # mais custam a fixar.
    lookup_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
