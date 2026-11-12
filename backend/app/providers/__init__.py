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
    if settings.azure_speech_key is None or not settings.azure_speech_region:
        raise RuntimeError(
            "READER_SPEECH_PROVIDER=azure precisa de AZURE_SPEECH_KEY e AZURE_SPEECH_REGION "
            "no ficheiro .env. Para correr sem conta no Azure, usa READER_SPEECH_PROVIDER=fake."
        )
    # Importado só aqui: quem usa a voz simulada não carrega o SDK do Azure.
    from app.providers.azure_speech import AzureSpeechSynthesizer

    return AzureSpeechSynthesizer(
        settings.azure_speech_key.get_secret_value(), settings.azure_speech_region
    )
