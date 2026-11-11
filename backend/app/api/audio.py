"""Rotas de áudio, de estimativa de custo e de consumo."""

import re

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import SessionDep, SettingsDep, SpeechDep, StorageDep
from app.api.schemas import (
    AudioEstimateOut,
    AudioRequest,
    BlockAudioOut,
    EstimateRequest,
    TimedWordOut,
    TtsUsageOut,
    UsageOut,
)
from app.audio.models import AudioAsset
from app.audio.service import estimate_audio, get_block_audio
from app.core.errors import ProblemError
from app.importing.models import Chapter, Document
from app.usage.service import get_tts_usage_summary

router = APIRouter(tags=["audio"])

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


@router.post("/blocks/{block_id}/audio", response_model=BlockAudioOut)
def request_block_audio(
    block_id: int,
    session: SessionDep,
    storage: StorageDep,
    speech: SpeechDep,
    settings: SettingsDep,
    body: AudioRequest | None = None,
) -> BlockAudioOut:
    """Devolve o áudio de um bloco, gerando-o se ainda não existir.

    É um POST e não um GET porque pode ter efeitos: gastar quota e, num
    documento privado, enviar texto para fora do portátil.
    """
    result = get_block_audio(
        session,
        storage,
        speech,
        settings,
        block_id,
        confirm_private=body.confirm_private if body else False,
    )
    asset = result.asset
    return BlockAudioOut(
        block_id=block_id,
        audio_url=f"/api/v1/audio/{asset.content_hash}",
        media_type=asset.media_type,
        duration_ms=asset.duration_ms,
        voice=asset.voice,
        cached=result.cached,
        words=[TimedWordOut.model_validate(word) for word in result.words],
    )


@router.get("/audio/{content_hash}")
def get_audio_file(
    content_hash: str, request: Request, session: SessionDep, storage: StorageDep
) -> Response:
    """Serve um ficheiro de áudio, inteiro ou só uma parte."""
    asset = None
    # Validar o formato antes de consultar: o valor vem do endereço.
    if _SHA256_HEX.fullmatch(content_hash):
        asset = session.scalar(select(AudioAsset).where(AudioAsset.content_hash == content_hash))
    if asset is None:
        raise ProblemError(404, "audio_not_found", "Áudio não encontrado", "Esse áudio não existe.")

    data = storage.read(asset.storage_key)
    headers = {
        "Accept-Ranges": "bytes",
        # O conteúdo de um hash nunca muda, por isso o browser pode guardá-lo
        # indefinidamente. "private": só o browser do utilizador, nunca um
        # intermediário.
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": f'"{content_hash}"',
    }

    # O browser pede partes do ficheiro com o cabeçalho Range ("bytes=1000-")
    # quando o utilizador salta para outro ponto do áudio. A resposta a um
    # pedido parcial é 206 e diz que parte vai.
    byte_range = _parse_range(request.headers.get("range"), len(data))
    if byte_range is None:
        return Response(data, media_type=asset.media_type, headers=headers)
    start, end = byte_range
    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    return Response(
        data[start : end + 1], status_code=206, media_type=asset.media_type, headers=headers
    )


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Converte "bytes=a-b" em (início, fim) inclusivos. None: enviar tudo."""
    match = _RANGE.fullmatch(header.strip()) if header else None
    if match is None or (not match[1] and not match[2]):
        # Sem cabeçalho, ou num formato que não tratamos (vários intervalos):
        # a norma permite ignorar e responder com o ficheiro inteiro.
        return None
    if match[1]:
        start = int(match[1])
        end = min(int(match[2]), size - 1) if match[2] else size - 1
    else:
        # "bytes=-500" quer dizer "os últimos 500 bytes".
        start = max(size - int(match[2]), 0)
        end = size - 1
    if start >= size or start > end:
        raise ProblemError(
            416, "range_not_satisfiable", "Intervalo inválido", "O intervalo pedido não existe."
        )
    return start, end


@router.post("/documents/{document_id}/audio/estimate", response_model=AudioEstimateOut)
def estimate_document_audio(
    document_id: int,
    session: SessionDep,
    speech: SpeechDep,
    settings: SettingsDep,
    body: EstimateRequest | None = None,
) -> AudioEstimateOut:
    """Caracteres e custo estimado do áudio de um capítulo ou do documento inteiro."""
    document = session.get(Document, document_id)
    if document is None:
        raise ProblemError(
            404,
            "document_not_found",
            "Documento não encontrado",
            "Não existe documento com esse id.",
        )
    chapter_position = body.chapter_position if body else None
    if chapter_position is not None:
        exists = session.scalar(
            select(Chapter.id).where(
                Chapter.document_id == document_id, Chapter.position == chapter_position
            )
        )
        if exists is None:
            raise ProblemError(
                404,
                "chapter_not_found",
                "Capítulo não encontrado",
                "O documento não tem esse capítulo.",
            )
    estimate = estimate_audio(session, speech, settings, document, chapter_position)
    return AudioEstimateOut.model_validate(estimate)


@router.get("/usage", response_model=UsageOut)
def get_usage(session: SessionDep, settings: SettingsDep) -> UsageOut:
    """Consumo de voz no mês corrente."""
    summary = get_tts_usage_summary(session, settings)
    return UsageOut(month=summary.month, tts=TtsUsageOut.model_validate(summary))
