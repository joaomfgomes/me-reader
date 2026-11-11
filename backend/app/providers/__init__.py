"""Único sítio com código de fornecedores externos (Azure AI Speech e LLM).

O resto da aplicação fala com interfaces próprias (voz, tutor) e nunca importa SDKs
externos diretamente. Trocar de fornecedor é implementar a interface aqui (ADR-003, ADR-005).
"""

from app.audio.voice import SpeechSynthesizer
from app.core.config import Settings
from app.providers.fake_speech import FakeSpeechSynthesizer


def create_speech_synthesizer(settings: Settings) -> SpeechSynthesizer:
    """Escolhe a implementação de voz indicada em READER_SPEECH_PROVIDER."""
    if settings.speech_provider == "fake":
        return FakeSpeechSynthesizer()
    # Falhar no arranque, com uma mensagem clara, é melhor do que arrancar e
    # só dar erro quando alguém carregar no botão de ouvir.
    raise RuntimeError(
        f"O fornecedor de voz '{settings.speech_provider}' ainda não está implementado. "
        "Usa READER_SPEECH_PROVIDER=fake."
    )
