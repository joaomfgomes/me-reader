"""Tabelas do áudio gerado."""

from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UtcDateTime


def _now() -> datetime:
    return datetime.now(UTC)


class AudioAsset(Base):
    """Um ficheiro de áudio e os tempos das suas palavras.

    É identificado pelo hash do conteúdo que o gerou (texto, voz e versão da
    limpeza) e não pelo bloco: o mesmo texto com a mesma voz dá sempre o mesmo
    áudio, venha de que documento vier. As linhas nunca são alteradas, só
    criadas ou apagadas (ADR-004).
    """

    __tablename__ = "audio_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(50))
    voice: Mapped[str] = mapped_column(String(100))
    media_type: Mapped[str] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(200))
    duration_ms: Mapped[int] = mapped_column(Integer)
    char_count: Mapped[int] = mapped_column(Integer)
    # Lista de [posição no texto, comprimento, início em ms, fim em ms], tal
    # como o serviço de voz os devolveu. O alinhamento com as nossas palavras
    # é calculado ao responder, para poder ser melhorado sem gerar áudio novo.
    timings: Mapped[list[list[int]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)


class BlockAudio(Base):
    """Regista que um bloco usa um áudio.

    Como o áudio é partilhado por hash, esta ligação é o que permite saber, ao
    apagar um documento, que áudio era só dele e pode ser apagado também.
    """

    __tablename__ = "block_audio"

    block_id: Mapped[int] = mapped_column(
        ForeignKey("blocks.id", ondelete="CASCADE"), primary_key=True
    )
    audio_asset_id: Mapped[int] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="CASCADE"), primary_key=True
    )
