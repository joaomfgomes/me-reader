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


# --- Áudio e consumo --------------------------------------------------------


class AudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Tem de vir a True para gerar áudio novo de um documento privado: é a
    # confirmação de que o texto pode ser enviado ao serviço de voz.
    confirm_private: bool = False


class TimedWordOut(ApiModel):
    # Posição da palavra no texto do bloco.
    start: int
    end: int
    # Quando é dita, em milissegundos desde o início do áudio. None se o
    # serviço de voz não devolveu tempo para esta palavra.
    start_ms: int | None
    end_ms: int | None


class BlockAudioOut(BaseModel):
    block_id: int
    audio_url: str
    media_type: str
    duration_ms: int
    voice: str
    # True se o áudio veio da cache, sem custo.
    cached: bool
    words: list[TimedWordOut]


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Sem capítulo, a estimativa é para o documento inteiro.
    chapter_position: int | None = None


class AudioEstimateOut(ApiModel):
    blocks_total: int
    blocks_cached: int
    characters_total: int
    characters_cached: int
    characters_to_synthesize: int
    # Estimativa com o preço configurado; não é um valor faturado.
    estimated_cost_usd: float
    characters_used_this_month: int
    monthly_character_limit: int
    exceeds_monthly_limit: bool


class TtsUsageOut(ApiModel):
    requests: int
    cache_hits: int
    # Entre 0 e 1; None se ainda não houve pedidos este mês.
    cache_hit_rate: float | None
    characters_synthesized: int
    characters_from_cache: int
    estimated_cost_usd: float
    monthly_character_limit: int
    characters_remaining: int


class UsageOut(BaseModel):
    # Mês a que os números dizem respeito, no formato "2026-11" (UTC).
    month: str
    tts: TtsUsageOut
