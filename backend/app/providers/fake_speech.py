"""Fornecedor de voz simulado: não fala, mas comporta-se como um que fala.

Serve para os testes (regra fixa 5: nenhum teste faz chamadas pagas) e para
desenvolver o leitor de áudio sem gastar quota. O "áudio" é um bip curto no
início de cada palavra, o suficiente para ouvir se o destaque está certo.
"""

import io
import math
import re
import wave

from app.audio.voice import SynthesisResult, WordTiming

_SAMPLE_RATE = 8000
# Duração simulada de cada palavra: uma base mais um pouco por letra.
_WORD_BASE_MS = 90
_MS_PER_CHAR = 55
_GAP_MS = 60
_PARAGRAPH_PAUSE_MS = 300
_TAIL_MS = 200

# De propósito, o simulador divide o texto de maneira diferente da nossa: para
# ele uma "palavra" é tudo o que está entre espaços, com a pontuação agarrada.
# Um serviço verdadeiro também não divide como nós, e assim os testes exercitam
# o alinhamento por posição no texto.
_TOKEN = re.compile(r"\S+")


def _beep() -> bytes:
    """30 ms de um tom de 440 Hz, em amostras de 8 bits."""
    samples = _SAMPLE_RATE * 30 // 1000
    # Em WAV de 8 bits o silêncio é o valor 128 e o som oscila à volta dele.
    return bytes(
        128 + round(40 * math.sin(2 * math.pi * 440 * index / _SAMPLE_RATE))
        for index in range(samples)
    )


_BEEP = _beep()


class FakeSpeechSynthesizer:
    """Implementação de SpeechSynthesizer que não faz chamadas externas."""

    name = "fake"

    def voice_for(self, language: str) -> str:
        return f"fake-{language}"

    def synthesize(self, text: str, voice: str) -> SynthesisResult:
        timings: list[WordTiming] = []
        cursor_ms = 0
        previous_end = 0
        for match in _TOKEN.finditer(text):
            # Uma quebra de parágrafo antes da palavra dá uma pausa maior.
            if "\n" in text[previous_end : match.start()]:
                cursor_ms += _PARAGRAPH_PAUSE_MS
            duration = _WORD_BASE_MS + _MS_PER_CHAR * len(match.group())
            timings.append(
                WordTiming(
                    text_offset=match.start(),
                    length=len(match.group()),
                    start_ms=cursor_ms,
                    end_ms=cursor_ms + duration,
                )
            )
            cursor_ms += duration + _GAP_MS
            previous_end = match.end()

        duration_ms = cursor_ms + _TAIL_MS
        return SynthesisResult(
            audio=_render_wav(duration_ms, [timing.start_ms for timing in timings]),
            media_type="audio/wav",
            file_extension="wav",
            duration_ms=duration_ms,
            timings=timings,
        )


def _render_wav(duration_ms: int, beep_starts_ms: list[int]) -> bytes:
    """Gera um WAV mono de 8 bits: silêncio com um bip em cada instante dado."""
    samples = bytearray(b"\x80" * (_SAMPLE_RATE * duration_ms // 1000))
    for start_ms in beep_starts_ms:
        position = _SAMPLE_RATE * start_ms // 1000
        samples[position : position + len(_BEEP)] = _BEEP

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(_SAMPLE_RATE)
        wav_file.writeframes(bytes(samples))
    return buffer.getvalue()
