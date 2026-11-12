"""Fornecedor de voz Azure AI Speech (ADR-003).

É o único ficheiro da aplicação que conhece o SDK do Azure. O SDK é
obrigatório porque a API REST do Azure devolve o áudio, mas não os tempos das
palavras; esses só chegam pelos eventos de "fronteira de palavra" do SDK.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from types import ModuleType
from typing import Any

from app.audio.voice import SpeechProviderError, SynthesisResult, WordTiming

logger = logging.getLogger(__name__)

# Uma voz Neural por língua. O nome da voz entra na chave de cache do áudio:
# trocar uma voz aqui gera áudio novo para essa língua, sem apagar o antigo.
VOICES = {
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
}

# O Azure mede o tempo em "ticks" de 100 nanossegundos: 10 000 por milissegundo.
_TICKS_PER_MS = 10_000


@dataclass(frozen=True)
class WordBoundary:
    """O que nos interessa de um evento de fronteira de palavra do Azure."""

    text: str
    text_offset: int
    word_length: int
    start_ms: int
    duration_ms: int


def timings_from_boundaries(
    text: str, boundaries: list[WordBoundary], audio_duration_ms: int
) -> list[WordTiming]:
    """Converte as fronteiras do Azure nos nossos tempos, por posição no texto.

    Está separada da chamada ao serviço para poder ser testada sem rede.

    Não confiamos cegamente na posição que o Azure indica: confirmamos que o
    texto nessa posição é mesmo a palavra do evento. Se não for (acontece com
    caracteres que o serviço trata de forma especial, como "&"), procuramos a
    palavra a partir do fim da anterior. Se nem assim aparecer, o evento é
    ignorado e essa palavra fica sem tempo, em vez de acender a palavra errada.
    """
    timings: list[WordTiming] = []
    cursor = 0
    for index, boundary in enumerate(boundaries):
        offset, length = boundary.text_offset, boundary.word_length
        if text[offset : offset + length] != boundary.text or length == 0:
            offset, length = text.find(boundary.text, cursor), len(boundary.text)
            if offset == -1 or length == 0:
                continue
        cursor = offset + length

        end_ms = boundary.start_ms + boundary.duration_ms
        if boundary.duration_ms <= 0:
            # Sem duração, a palavra acaba quando a seguinte começa.
            following = boundaries[index + 1 :]
            end_ms = following[0].start_ms if following else audio_duration_ms
        timings.append(
            WordTiming(
                text_offset=offset,
                length=length,
                start_ms=boundary.start_ms,
                end_ms=max(boundary.start_ms, min(end_ms, audio_duration_ms)),
            )
        )
    # O alinhamento com as nossas palavras espera a lista por ordem de posição.
    return sorted(timings, key=lambda timing: timing.text_offset)


def _to_ms(value: Any) -> int:
    """Converte uma duração do SDK, que pode vir como timedelta ou em ticks."""
    if isinstance(value, timedelta):
        return round(value.total_seconds() * 1000)
    return round(value / _TICKS_PER_MS)


class AzureSpeechSynthesizer:
    """Implementação de SpeechSynthesizer com o Azure AI Speech."""

    name = "azure"

    def __init__(self, key: str, region: str, sdk: ModuleType | None = None) -> None:
        self._key = key
        self._region = region
        if sdk is None:
            # Importado aqui, e não no topo do ficheiro, para a biblioteca
            # nativa do Azure só ser carregada quando este fornecedor é usado.
            # Os testes passam um SDK a fingir no parâmetro "sdk".
            import azure.cognitiveservices.speech as sdk
        self._sdk = sdk

    def voice_for(self, language: str) -> str:
        return VOICES[language]

    def synthesize(self, text: str, voice: str) -> SynthesisResult:
        sdk = self._sdk
        config = sdk.SpeechConfig(subscription=self._key, region=self._region)
        config.speech_synthesis_voice_name = voice
        config.set_speech_synthesis_output_format(
            sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )
        # audio_config=None: o áudio vem em memória, em vez de tocar nas
        # colunas do computador onde o servidor corre.
        synthesizer = sdk.SpeechSynthesizer(speech_config=config, audio_config=None)

        # O SDK chama esta função, numa thread dele, por cada palavra, sinal de
        # pontuação e frase. list.append é seguro entre threads em Python.
        events: list[Any] = []
        synthesizer.synthesis_word_boundary.connect(events.append)

        # Enviamos texto simples e não SSML, para as posições devolvidas se
        # referirem ao texto do bloco tal como o temos. .get() espera pelo fim.
        try:
            result = synthesizer.speak_text_async(text).get()
        except Exception as exc:
            logger.warning("azure_speech_failed", extra={"error_type": type(exc).__name__})
            raise SpeechProviderError("azure: falha ao contactar o serviço") from exc

        if result.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            details = result.cancellation_details
            code = getattr(getattr(details, "error_code", None), "name", "Unknown")
            # Só o nome do código de erro. O texto de detalhe do Azure pode
            # trazer endereços e identificadores, e não vai para os logs.
            logger.warning("azure_speech_canceled", extra={"error_code": code})
            raise SpeechProviderError(f"azure: síntese cancelada ({code})")

        duration_ms = _to_ms(result.audio_duration)
        boundaries = [
            WordBoundary(
                text=event.text,
                text_offset=event.text_offset,
                word_length=event.word_length,
                start_ms=_to_ms(event.audio_offset),
                duration_ms=_to_ms(event.duration),
            )
            for event in events
            # Pontuação e inícios de frase também geram eventos; só as
            # palavras nos interessam.
            if event.boundary_type == sdk.SpeechSynthesisBoundaryType.Word
        ]
        # Os eventos podem chegar fora de ordem; ordenamos pelo instante.
        boundaries.sort(key=lambda boundary: boundary.start_ms)
        return SynthesisResult(
            audio=result.audio_data,
            media_type="audio/mpeg",
            file_extension="mp3",
            duration_ms=duration_ms,
            timings=timings_from_boundaries(text, boundaries, duration_ms),
        )
