"""Interface de voz: o que a aplicação precisa de um serviço de síntese.

O resto da app só conhece este ficheiro. As implementações concretas (o
simulador e o Azure) vivem em app/providers/ e podem ser
trocadas sem mexer em mais nada (ADR-003).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True)
class WordTiming:
    """Quando é dita uma palavra, e onde ela está no texto enviado.

    A palavra é identificada pela posição no texto (text_offset e length) e
    não pela ordem. Um serviço de voz não divide o texto como nós: pode juntar
    "p.m." numa palavra ou ler "1865" como quatro. Pela posição conseguimos
    sempre saber a que palavra nossa corresponde cada tempo.
    """

    text_offset: int
    length: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    # Tipo do ficheiro de áudio, por exemplo "audio/mpeg", e a extensão
    # correspondente, para o guardar em disco.
    media_type: str
    file_extension: str
    duration_ms: int
    timings: list[WordTiming]


class SpeechProviderError(Exception):
    """O serviço de voz falhou ou está indisponível.

    As implementações convertem os erros próprios do fornecedor nesta exceção,
    para quem as usa não precisar de conhecer nenhum SDK.
    """


class SpeechSynthesizer(Protocol):
    # Nome do fornecedor, só para registo ("fake", "azure").
    name: str

    def voice_for(self, language: str) -> str:
        """Identificador da voz usada para uma língua ("en", "es", ...).

        O identificador entra na chave de cache do áudio: mudar de voz gera
        áudio novo em vez de reutilizar o antigo.
        """
        ...

    def synthesize(self, text: str, voice: str) -> SynthesisResult:
        """Converte o texto em áudio. Lança SpeechProviderError se falhar."""
        ...


class TrackedSynthesizer:
    """Embrulha um fornecedor de voz e lembra-se de quando falhou pela última vez.

    É o que permite ao /health dizer "degradado" quando o serviço de voz está
    com problemas, sem fazer chamadas (pagas) só para o testar. O padrão
    chama-se "decorator": tem a mesma interface do objeto embrulhado e
    acrescenta-lhe um comportamento, sem que ele ou quem o usa tenham de mudar.
    """

    def __init__(self, inner: SpeechSynthesizer) -> None:
        self._inner = inner
        self.name = inner.name
        self.last_failure_at: datetime | None = None

    def voice_for(self, language: str) -> str:
        return self._inner.voice_for(language)

    def synthesize(self, text: str, voice: str) -> SynthesisResult:
        try:
            result = self._inner.synthesize(text, voice)
        except SpeechProviderError:
            self.last_failure_at = datetime.now(UTC)
            raise
        # Uma síntese bem-sucedida mostra que o serviço recuperou.
        self.last_failure_at = None
        return result
