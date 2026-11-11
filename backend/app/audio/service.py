"""Áudio de um bloco: devolver o que está em cache ou sintetizar e guardar."""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audio.alignment import TimedWord, align_timings
from app.audio.models import AudioAsset, BlockAudio
from app.audio.voice import SpeechProviderError, SpeechSynthesizer, WordTiming
from app.core.config import Settings
from app.core.errors import ProblemError
from app.importing.models import Block, Chapter, Document
from app.storage.base import FileStorage
from app.usage.service import estimate_tts_cost, record_tts_usage, tts_characters_this_month

logger = logging.getLogger(__name__)

# Um cadeado por chave de cache, para dois pedidos simultâneos do mesmo bloco
# não pagarem duas sínteses: o segundo espera pelo primeiro e encontra o áudio
# já em cache. Funciona porque há um só processo (ADR-001).
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def audio_cache_key(text: str, voice: str, cleaning_version: int) -> str:
    """Chave de cache do áudio (ADR-004): hash de tudo o que muda o resultado.

    A velocidade de leitura não entra: é aplicada no browser sobre o mesmo
    ficheiro. Usamos JSON para juntar as partes porque uma simples
    concatenação seria ambígua ("ab" + "c" e "a" + "bc" dariam o mesmo).
    """
    payload = json.dumps([text, voice, cleaning_version], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BlockAudioResult:
    asset: AudioAsset
    # True se o áudio já existia e nada foi pedido ao serviço de voz.
    cached: bool
    words: list[TimedWord]


def _load_block(session: Session, block_id: int) -> tuple[Block, Document]:
    row = session.execute(
        select(Block, Document)
        .join(Chapter, Block.chapter_id == Chapter.id)
        .join(Document, Chapter.document_id == Document.id)
        .where(Block.id == block_id)
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "block_not_found", "Bloco não encontrado", "Esse bloco não existe.")
    return row.Block, row.Document


def require_language(document: Document) -> str:
    if document.language is None:
        raise ProblemError(
            422,
            "language_required",
            "Falta a língua do documento",
            "Escolhe a língua do documento na biblioteca antes de pedir áudio.",
        )
    return document.language


def get_block_audio(
    session: Session,
    storage: FileStorage,
    speech: SpeechSynthesizer,
    settings: Settings,
    block_id: int,
    *,
    confirm_private: bool = False,
) -> BlockAudioResult:
    """Devolve o áudio de um bloco, sintetizando-o só se ainda não existir."""
    block, document = _load_block(session, block_id)
    voice = speech.voice_for(require_language(document))
    # A versão da limpeza é a do documento, guardada quando foi importado, e
    # não a atual: o áudio corresponde ao texto que está na base de dados.
    key = audio_cache_key(block.text, voice, document.cleaning_version)

    with _lock_for(key):
        asset = session.scalar(select(AudioAsset).where(AudioAsset.content_hash == key))
        cached = asset is not None
        if asset is None:
            asset = _synthesize(
                session, storage, speech, settings, block, document, voice, key, confirm_private
            )

        _link(session, block.id, asset.id)
        record_tts_usage(
            session,
            settings,
            provider=asset.provider,
            document_id=document.id,
            characters=asset.char_count,
            cache_hit=cached,
        )
        session.commit()

    words = [(start, end) for sentence in block.sentences for start, end in sentence.words]
    timings = [WordTiming(*timing) for timing in asset.timings]
    return BlockAudioResult(asset=asset, cached=cached, words=align_timings(words, timings))


def _synthesize(
    session: Session,
    storage: FileStorage,
    speech: SpeechSynthesizer,
    settings: Settings,
    block: Block,
    document: Document,
    voice: str,
    key: str,
    confirm_private: bool,
) -> AudioAsset:
    # Só chegamos aqui quando o texto vai mesmo sair do portátil. Áudio que já
    # está em cache toca sem confirmação, porque nada é enviado.
    if document.is_private and not confirm_private:
        raise ProblemError(
            409,
            "private_document_confirmation_required",
            "Documento privado",
            "Este documento está marcado como privado. Para gerar áudio, o texto deste "
            "bloco é enviado ao serviço de voz; confirma para continuar.",
            characters=block.char_count,
        )

    used = tts_characters_this_month(session)
    if used + block.char_count > settings.monthly_tts_char_limit:
        raise ProblemError(
            429,
            "tts_quota_exceeded",
            "Teto mensal de voz atingido",
            "O áudio que já foi gerado continua disponível. O teto volta a zero no "
            "início do próximo mês, ou podes aumentá-lo no ficheiro .env.",
            monthly_character_limit=settings.monthly_tts_char_limit,
            characters_used=used,
        )

    started_at = time.perf_counter()
    try:
        result = speech.synthesize(block.text, voice)
    except SpeechProviderError as exc:
        logger.warning("tts_provider_error", extra={"block_id": block.id, "provider": speech.name})
        raise ProblemError(
            502,
            "tts_provider_error",
            "O serviço de voz falhou",
            "Não foi possível gerar o áudio. Tenta outra vez daqui a pouco.",
        ) from exc

    storage_key = f"audio/{key}.{result.file_extension}"
    storage.save(storage_key, result.audio)
    asset = AudioAsset(
        content_hash=key,
        provider=speech.name,
        voice=voice,
        media_type=result.media_type,
        storage_key=storage_key,
        duration_ms=result.duration_ms,
        char_count=block.char_count,
        timings=[[t.text_offset, t.length, t.start_ms, t.end_ms] for t in result.timings],
    )
    session.add(asset)
    try:
        # flush envia o INSERT sem fechar a transação: ficamos a saber o id do
        # áudio e se a restrição de unicidade do hash foi respeitada.
        session.flush()
    except IntegrityError:
        # Outro processo gravou o mesmo áudio entretanto. Com um só processo o
        # cadeado impede-o, mas a base de dados é a última garantia.
        session.rollback()
        return session.scalars(select(AudioAsset).where(AudioAsset.content_hash == key)).one()

    # Só identificadores, tamanhos e tempos; nunca o texto (regra fixa 9).
    logger.info(
        "audio_synthesized",
        extra={
            "block_id": block.id,
            "document_id": document.id,
            "provider": speech.name,
            "characters": block.char_count,
            "audio_bytes": len(result.audio),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
        },
    )
    return asset


def _link(session: Session, block_id: int, asset_id: int) -> None:
    if session.get(BlockAudio, (block_id, asset_id)) is None:
        session.add(BlockAudio(block_id=block_id, audio_asset_id=asset_id))


# --- Estimativa -------------------------------------------------------------


@dataclass(frozen=True)
class AudioEstimate:
    blocks_total: int
    blocks_cached: int
    characters_total: int
    characters_cached: int
    estimated_cost_usd: float
    characters_used_this_month: int
    monthly_character_limit: int

    @property
    def characters_to_synthesize(self) -> int:
        return self.characters_total - self.characters_cached

    @property
    def exceeds_monthly_limit(self) -> bool:
        total = self.characters_used_this_month + self.characters_to_synthesize
        return total > self.monthly_character_limit


def estimate_audio(
    session: Session,
    speech: SpeechSynthesizer,
    settings: Settings,
    document: Document,
    chapter_position: int | None = None,
) -> AudioEstimate:
    """Quanto custaria gerar o áudio de um capítulo, ou do documento inteiro.

    Não gera nada nem envia texto a ninguém: só conta caracteres e vê o que já
    está em cache.
    """
    voice = speech.voice_for(require_language(document))
    query = (
        select(Block.text, Block.char_count)
        .join(Chapter, Block.chapter_id == Chapter.id)
        .where(Chapter.document_id == document.id)
    )
    if chapter_position is not None:
        query = query.where(Chapter.position == chapter_position)
    blocks = session.execute(query).all()

    # Para cada bloco, a chave que o seu áudio teria e o número de caracteres.
    keyed = [
        (audio_cache_key(text, voice, document.cleaning_version), char_count)
        for text, char_count in blocks
    ]
    cached_keys = _existing_keys(session, list({key for key, _ in keyed}))
    cached_sizes = [char_count for key, char_count in keyed if key in cached_keys]
    characters_total = sum(char_count for _, char_count in keyed)
    return AudioEstimate(
        blocks_total=len(keyed),
        blocks_cached=len(cached_sizes),
        characters_total=characters_total,
        characters_cached=sum(cached_sizes),
        estimated_cost_usd=estimate_tts_cost(characters_total - sum(cached_sizes), settings),
        characters_used_this_month=tts_characters_this_month(session),
        monthly_character_limit=settings.monthly_tts_char_limit,
    )


def _existing_keys(session: Session, keys: list[str]) -> set[str]:
    # As bases de dados limitam o número de valores numa cláusula IN, por isso
    # perguntamos em grupos de 500.
    found: set[str] = set()
    for start in range(0, len(keys), 500):
        chunk = keys[start : start + 500]
        found.update(
            session.scalars(
                select(AudioAsset.content_hash).where(AudioAsset.content_hash.in_(chunk))
            )
        )
    return found


# --- Limpeza ao apagar um documento -----------------------------------------


def audio_asset_ids_of_document(session: Session, document_id: int) -> list[int]:
    return list(
        session.scalars(
            select(BlockAudio.audio_asset_id)
            .join(Block, BlockAudio.block_id == Block.id)
            .join(Chapter, Block.chapter_id == Chapter.id)
            .where(Chapter.document_id == document_id)
            .distinct()
        )
    )


def delete_unused_audio(session: Session, storage: FileStorage, asset_ids: list[int]) -> int:
    """Apaga, da lista dada, o áudio que já nenhum bloco usa. Devolve quantos apagou.

    Chama-se depois de apagar um documento. Áudio partilhado com outro
    documento (o mesmo texto com a mesma voz) continua a ter ligações e fica.
    """
    deleted = 0
    for asset_id in asset_ids:
        still_used = session.scalar(
            select(BlockAudio.block_id).where(BlockAudio.audio_asset_id == asset_id).limit(1)
        )
        asset = session.get(AudioAsset, asset_id)
        if still_used is None and asset is not None:
            storage_key = asset.storage_key
            session.delete(asset)
            session.commit()
            storage.delete(storage_key)
            deleted += 1
    return deleted
