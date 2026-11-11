"""Formas dos pedidos e das respostas da API de documentos.

São modelos Pydantic separados dos modelos da base de dados de propósito: a
API é um contrato com o frontend e só deve mudar quando decidirmos, não por
arrasto sempre que se mexe numa tabela. Campos internos como file_hash e
storage_key não aparecem aqui.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    # from_attributes deixa construir a resposta diretamente a partir de um
    # objeto do SQLAlchemy, lendo os atributos com o mesmo nome.
    model_config = ConfigDict(from_attributes=True)


class DocumentSummary(ApiModel):
    id: int
    title: str
    author: str | None
    language: str | None
    format: str
    is_private: bool
    file_size: int
    created_at: datetime
    # Hoje a importação é síncrona e o documento está sempre pronto quando a
    # resposta chega. O campo existe para o contrato não mudar se a importação
    # passar a correr em fundo (por exemplo com PDFs, na Fase 5).
    status: Literal["ready"] = "ready"


class ChapterSummary(ApiModel):
    position: int
    title: str | None


class ReadingPositionOut(BaseModel):
    sentence_id: int
    block_id: int
    # Posição do capítulo, para o leitor saber qual abrir.
    chapter_position: int
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    chapters: list[ChapterSummary]
    reading_position: ReadingPositionOut | None


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    # Valor a enviar em ?cursor= para pedir a página seguinte; None na última.
    next_cursor: str | None


class DocumentUpdate(BaseModel):
    # extra="forbid": um campo desconhecido no pedido dá erro em vez de ser
    # ignorado em silêncio. Apanha enganos como "private" em vez de "is_private".
    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    is_private: bool | None = None


class SentenceOut(ApiModel):
    id: int
    position: int
    text: str
    # Posições no texto do bloco: block.text[start_offset:end_offset].
    start_offset: int
    end_offset: int
    # Pares [início, fim] de cada palavra, também no texto do bloco.
    words: list[tuple[int, int]]


class BlockOut(ApiModel):
    id: int
    position: int
    # Parágrafos separados por "\n".
    text: str
    sentences: list[SentenceOut]


class ChapterDetail(ApiModel):
    document_id: int
    position: int
    title: str | None
    blocks: list[BlockOut]


class PositionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: int
