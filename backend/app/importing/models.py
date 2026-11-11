"""Tabelas do documento importado: documento, capítulos, blocos e frases.

Ficam neste módulo porque é a importação que as cria. Os outros módulos
(áudio, tutor, vocabulário) vão lê-las, mas não lhes alteram o texto.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(500))
    # Código ISO 639-1 ("en", "es", ...). Fica vazio se não foi possível
    # detetar; o utilizador pode corrigir.
    language: Mapped[str | None] = mapped_column(String(8))
    format: Mapped[str] = mapped_column(String(10))
    # SHA-256 do ficheiro original. O "unique" impede guardar o mesmo livro
    # duas vezes, e é por este valor que se reconhece uma reimportação.
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    file_size: Mapped[int] = mapped_column(Integer)
    # Onde está o original, como chave da interface de armazenamento.
    storage_key: Mapped[str] = mapped_column(String(200))
    is_private: Mapped[bool] = mapped_column(default=False)
    # Versão da limpeza de texto com que foi importado (ver cleaning.py).
    cleaning_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # "relationship" não cria colunas: dá acesso aos capítulos como uma lista
    # Python. O cascade faz com que apagar o documento apague também os filhos.
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Chapter.position"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    # Não pode haver dois capítulos na mesma posição do mesmo documento. Esta
    # restrição cria também o índice que torna rápido listar os capítulos de
    # um documento por ordem.
    __table_args__ = (UniqueConstraint("document_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # ondelete="CASCADE" repete na base de dados a regra do cascade do ORM,
    # para valer mesmo quando a linha é apagada por SQL direto.
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))

    document: Mapped[Document] = relationship(back_populates="chapters")
    blocks: Mapped[list["Block"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="Block.position"
    )


class Block(Base):
    """Alguns parágrafos seguidos, separados por "\\n". É a unidade de síntese de áudio."""

    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("chapter_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Guardado à parte para estimar custos de áudio sem ler o texto todo.
    char_count: Mapped[int] = mapped_column(Integer)

    chapter: Mapped[Chapter] = relationship(back_populates="blocks")
    sentences: Mapped[list["Sentence"]] = relationship(
        back_populates="block", cascade="all, delete-orphan", order_by="Sentence.position"
    )


class Sentence(Base):
    __tablename__ = "sentences"
    __table_args__ = (UniqueConstraint("block_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Posição da frase no texto do bloco: block.text[start_offset:end_offset].
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    # Lista de pares [início, fim] de cada palavra, também nas coordenadas do
    # bloco. Uma coluna JSON evita uma tabela com dezenas de milhares de linhas
    # por livro, e o tipo JSON do SQLAlchemy funciona em SQLite e em Postgres.
    words: Mapped[list[list[int]]] = mapped_column(JSON)

    block: Mapped[Block] = relationship(back_populates="sentences")
