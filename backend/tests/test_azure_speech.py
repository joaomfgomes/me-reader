"""Testes do fornecedor Azure, sem falar com o Azure.

A conversão dos eventos em tempos é testada com eventos escritos à mão, alguns
copiados do que o serviço devolveu no "make voice-check". A chamada ao serviço
é substituída por um SDK a fingir, com a mesma forma do verdadeiro.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.audio.voice import SpeechProviderError
from app.core.config import Settings
from app.providers import create_speech_synthesizer
from app.providers.azure_speech import (
    VOICES,
    AzureSpeechSynthesizer,
    WordBoundary,
    timings_from_boundaries,
)
from app.providers.fake_speech import FakeSpeechSynthesizer

# --- Conversão de fronteiras em tempos --------------------------------------


def boundary(text: str, offset: int, start_ms: int, duration_ms: int = 300) -> WordBoundary:
    return WordBoundary(text, offset, len(text), start_ms, duration_ms)


def pieces(text: str, timings: list) -> list[str]:
    return [text[t.text_offset : t.text_offset + t.length] for t in timings]


def test_boundaries_become_timings_at_the_same_positions() -> None:
    text = "The cat sat."
    boundaries = [boundary("The", 0, 50), boundary("cat", 4, 400), boundary("sat", 8, 800)]

    timings = timings_from_boundaries(text, boundaries, 1500)

    assert pieces(text, timings) == ["The", "cat", "sat"]
    assert [(t.start_ms, t.end_ms) for t in timings] == [(50, 350), (400, 700), (800, 1100)]


def test_multi_word_boundaries_from_the_real_service_are_kept_whole() -> None:
    # O Azure junta "in 1865" e "$3.50" num só evento cada.
    text = "printed in 1865, cost $3.50 & sold"
    boundaries = [
        boundary("printed", 0, 0),
        boundary("in 1865", 8, 400, 900),
        boundary("cost", 17, 1500),
        boundary("$3.50", 22, 1900, 800),
        boundary("&", 28, 2800, 200),
        boundary("sold", 30, 3100),
    ]

    timings = timings_from_boundaries(text, boundaries, 4000)

    assert pieces(text, timings) == ["printed", "in 1865", "cost", "$3.50", "&", "sold"]


def test_wrong_offset_is_corrected_by_searching_for_the_word() -> None:
    # O serviço diz que "sold" está na posição 20, mas está na 12.
    text = "cost $3 &amp sold"
    boundaries = [boundary("cost", 0, 0), boundary("sold", 20, 900)]

    timings = timings_from_boundaries(text, boundaries, 2000)

    assert pieces(text, timings) == ["cost", "sold"]
    assert timings[1].text_offset == text.index("sold")


def test_repeated_words_are_matched_in_order() -> None:
    text = "the cat and the dog"
    # Posições erradas nos dois "the": a procura tem de avançar, não repetir.
    boundaries = [boundary("the", 99, 0), boundary("cat", 4, 300), boundary("the", 99, 900)]

    timings = timings_from_boundaries(text, boundaries, 2000)

    assert [t.text_offset for t in timings] == [0, 4, 12]


def test_boundary_that_is_not_in_the_text_is_dropped() -> None:
    text = "The cat sat."
    boundaries = [boundary("The", 0, 0), boundary("dog", 4, 400), boundary("sat", 8, 800)]

    assert pieces(text, timings_from_boundaries(text, boundaries, 1500)) == ["The", "sat"]


def test_missing_duration_ends_when_the_next_word_starts() -> None:
    text = "The cat"
    boundaries = [boundary("The", 0, 100, 0), boundary("cat", 4, 600, 0)]

    timings = timings_from_boundaries(text, boundaries, 1500)

    assert [(t.start_ms, t.end_ms) for t in timings] == [(100, 600), (600, 1500)]


def test_word_never_ends_after_the_audio() -> None:
    timings = timings_from_boundaries("cat", [boundary("cat", 0, 900, 5000)], 1200)

    assert timings[0].end_ms == 1200


# --- Chamada ao serviço, com um SDK a fingir --------------------------------


class FakeSdk:
    """Imita a parte do SDK do Azure que o fornecedor usa."""

    ResultReason = SimpleNamespace(SynthesizingAudioCompleted="completed", Canceled="canceled")
    SpeechSynthesisBoundaryType = SimpleNamespace(
        Word="word", Punctuation="punctuation", Sentence="sentence"
    )
    SpeechSynthesisOutputFormat = SimpleNamespace(Audio24Khz48KBitRateMonoMp3="mp3-24k")

    def __init__(self, events: list, result: object | None = None, error: Exception | None = None):
        self.events = events
        self.result = result
        self.error = error
        self.configs: list = []
        self.spoken: list[str] = []

    def SpeechConfig(self, subscription: str, region: str):  # noqa: N802 - nome do SDK
        config = SimpleNamespace(
            subscription=subscription,
            region=region,
            speech_synthesis_voice_name=None,
            output_format=None,
        )
        config.set_speech_synthesis_output_format = lambda fmt: setattr(
            config, "output_format", fmt
        )
        self.configs.append(config)
        return config

    def SpeechSynthesizer(self, speech_config, audio_config):  # noqa: N802 - nome do SDK
        sdk = self
        assert audio_config is None
        callbacks: list = []

        def speak_text_async(text: str):
            sdk.spoken.append(text)

            def get():
                if sdk.error:
                    raise sdk.error
                for event in sdk.events:
                    for callback in callbacks:
                        callback(event)
                return sdk.result

            return SimpleNamespace(get=get)

        return SimpleNamespace(
            synthesis_word_boundary=SimpleNamespace(connect=callbacks.append),
            speak_text_async=speak_text_async,
        )


def event(text: str, offset: int, start_ms: int, kind: str = "word") -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        text_offset=offset,
        word_length=len(text),
        # O SDK dá o instante em ticks de 100 ns e a duração como timedelta.
        audio_offset=start_ms * 10_000,
        duration=timedelta(milliseconds=300),
        boundary_type=kind,
    )


def completed(audio: bytes = b"mp3-bytes", seconds: float = 2.0) -> SimpleNamespace:
    return SimpleNamespace(
        reason="completed", audio_data=audio, audio_duration=timedelta(seconds=seconds)
    )


def test_synthesize_returns_audio_duration_and_word_timings() -> None:
    text = "The cat sat."
    sdk = FakeSdk(
        events=[
            event("The cat sat.", 0, 0, kind="sentence"),
            event("The", 0, 50),
            event("cat", 4, 400),
            event("sat", 8, 800),
            event(".", 11, 1100, kind="punctuation"),
        ],
        result=completed(),
    )
    speech = AzureSpeechSynthesizer("chave-de-teste", "westeurope", sdk=sdk)

    result = speech.synthesize(text, "en-US-JennyNeural")

    assert result.audio == b"mp3-bytes"
    assert (result.media_type, result.file_extension) == ("audio/mpeg", "mp3")
    assert result.duration_ms == 2000
    # Só as palavras: a frase e a pontuação também geram eventos, mas não contam.
    assert pieces(text, result.timings) == ["The", "cat", "sat"]
    assert [(t.start_ms, t.end_ms) for t in result.timings] == [(50, 350), (400, 700), (800, 1100)]


def test_request_uses_the_configured_key_region_voice_and_plain_text() -> None:
    sdk = FakeSdk(events=[], result=completed())
    speech = AzureSpeechSynthesizer("chave-de-teste", "westeurope", sdk=sdk)

    speech.synthesize("Line one.\nLine two.", "fr-FR-DeniseNeural")

    (config,) = sdk.configs
    assert (config.subscription, config.region) == ("chave-de-teste", "westeurope")
    assert config.speech_synthesis_voice_name == "fr-FR-DeniseNeural"
    assert config.output_format == "mp3-24k"
    # O texto segue tal como está, para as posições devolvidas lhe corresponderem.
    assert sdk.spoken == ["Line one.\nLine two."]


def test_events_out_of_order_are_sorted_by_time() -> None:
    text = "The cat"
    sdk = FakeSdk(events=[event("cat", 4, 400), event("The", 0, 50)], result=completed())

    result = AzureSpeechSynthesizer("k", "r", sdk=sdk).synthesize(text, "v")

    assert pieces(text, result.timings) == ["The", "cat"]


@pytest.mark.parametrize("error_code", ["AuthenticationFailure", "TooManyRequests", "Forbidden"])
def test_canceled_synthesis_becomes_a_provider_error_without_secrets(
    error_code: str, caplog: pytest.LogCaptureFixture
) -> None:
    canceled = SimpleNamespace(
        reason="canceled",
        cancellation_details=SimpleNamespace(
            error_code=SimpleNamespace(name=error_code),
            # O texto de detalhe do Azure pode trazer dados que não queremos nos logs.
            error_details="WebSocket upgrade failed, key=chave-de-teste endpoint=wss://x",
        ),
    )
    speech = AzureSpeechSynthesizer("chave-de-teste", "westeurope", sdk=FakeSdk([], canceled))

    with caplog.at_level("WARNING"), pytest.raises(SpeechProviderError) as error:
        speech.synthesize("The cat sat.", "en-US-JennyNeural")

    assert error_code in str(error.value)
    assert "chave-de-teste" not in str(error.value)
    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert error_code in logged
    assert "chave-de-teste" not in logged
    assert "cat sat" not in logged


def test_sdk_exception_becomes_a_provider_error() -> None:
    sdk = FakeSdk([], error=RuntimeError("ligação recusada"))

    with pytest.raises(SpeechProviderError):
        AzureSpeechSynthesizer("k", "r", sdk=sdk).synthesize("The cat.", "v")


def test_there_is_a_voice_for_each_supported_language() -> None:
    speech = AzureSpeechSynthesizer("k", "r", sdk=FakeSdk([]))

    assert {language: speech.voice_for(language) for language in VOICES} == VOICES
    assert set(VOICES) == {"en", "es", "fr", "de", "it"}
    # O nome da voz começa pela língua: "en-US-...", "fr-FR-...".
    assert all(voice.startswith(f"{language}-") for language, voice in VOICES.items())


# --- Escolha do fornecedor pela configuração --------------------------------


def settings_with(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


def test_fake_is_the_default_provider() -> None:
    assert isinstance(create_speech_synthesizer(settings_with()), FakeSpeechSynthesizer)


def test_azure_provider_is_created_from_the_settings() -> None:
    settings = settings_with(
        speech_provider="azure", AZURE_SPEECH_KEY="chave-de-teste", AZURE_SPEECH_REGION="westeurope"
    )

    speech = create_speech_synthesizer(settings)

    assert speech.name == "azure"
    assert speech.voice_for("de") == "de-DE-KatjaNeural"


@pytest.mark.parametrize(
    "missing",
    [{"AZURE_SPEECH_KEY": "chave-de-teste"}, {"AZURE_SPEECH_REGION": "westeurope"}, {}],
)
def test_azure_without_key_or_region_refuses_to_start(missing: dict) -> None:
    with pytest.raises(RuntimeError, match="AZURE_SPEECH_KEY"):
        create_speech_synthesizer(settings_with(speech_provider="azure", **missing))


def test_the_key_is_hidden_when_settings_are_printed() -> None:
    settings = settings_with(AZURE_SPEECH_KEY="chave-de-teste")

    assert "chave-de-teste" not in repr(settings)
    assert "chave-de-teste" not in str(settings.azure_speech_key)
