"""Testes do áudio: cache por hash, alinhamento, teto mensal, estimativa e consumo.

Nenhum teste fala com um serviço de voz verdadeiro: usam o simulador, numa
versão que regista as chamadas para se poder confirmar quando houve síntese.
"""

import io
import logging
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audio.alignment import TimedWord, align_timings
from app.audio.service import audio_cache_key, get_block_audio
from app.audio.voice import (
    SpeechProviderError,
    SynthesisResult,
    TrackedSynthesizer,
    WordTiming,
)
from app.core.config import Settings
from app.providers.fake_speech import FakeSpeechSynthesizer
from tests.epub_factory import make_epub

PROBLEM_JSON = "application/problem+json"


class RecordingSynthesizer(FakeSpeechSynthesizer):
    """O simulador, mas a registar cada chamada e capaz de falhar ou demorar."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = False
        self.delay_seconds = 0.0

    def synthesize(self, text: str, voice: str) -> SynthesisResult:
        self.calls.append((text, voice))
        time.sleep(self.delay_seconds)
        if self.fail:
            raise SpeechProviderError("serviço em baixo")
        return super().synthesize(text, voice)


@pytest.fixture
def speech(app: FastAPI) -> RecordingSynthesizer:
    # Substitui o fornecedor de voz da aplicação pelo que regista as chamadas.
    synthesizer = RecordingSynthesizer()
    app.state.speech = synthesizer
    return synthesizer


def upload(client: TestClient, data: bytes) -> dict:
    response = client.post("/api/v1/documents", files={"file": ("b.epub", data)})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def book(client: TestClient) -> dict:
    """Um livro pequeno, com dois capítulos de um bloco cada."""
    return upload(client, make_epub())


def blocks_of(client: TestClient, document_id: int, chapter: int = 0) -> list[dict]:
    return client.get(f"/api/v1/documents/{document_id}/chapters/{chapter}").json()["blocks"]


def block_id_of(client: TestClient, document_id: int, chapter: int = 0) -> int:
    return blocks_of(client, document_id, chapter)[0]["id"]


def request_audio(client: TestClient, block_id: int, **body: object):
    return client.post(f"/api/v1/blocks/{block_id}/audio", json=body or None)


# --- Síntese e cache --------------------------------------------------------


def test_first_request_synthesizes_and_returns_word_times(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    block = blocks_of(client, book["id"])[0]

    response = request_audio(client, block["id"])

    assert response.status_code == 200
    audio = response.json()
    assert audio["cached"] is False
    assert audio["voice"] == "fake-en"
    assert audio["duration_ms"] > 0
    assert len(speech.calls) == 1
    # O texto enviado é exatamente o do bloco, para as posições coincidirem.
    assert speech.calls[0] == (block["text"], "fake-en")

    # Há um tempo para cada palavra do bloco, pela mesma ordem e posições.
    block_words = [tuple(word) for sentence in block["sentences"] for word in sentence["words"]]
    assert [(word["start"], word["end"]) for word in audio["words"]] == block_words
    starts = [word["start_ms"] for word in audio["words"]]
    assert starts == sorted(starts)
    for word in audio["words"]:
        assert 0 <= word["start_ms"] < word["end_ms"] <= audio["duration_ms"]


def test_second_request_comes_from_the_cache(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    block_id = block_id_of(client, book["id"])

    first = request_audio(client, block_id).json()
    second = request_audio(client, block_id).json()

    assert second["cached"] is True
    assert second["audio_url"] == first["audio_url"]
    assert second["words"] == first["words"]
    # Regra fixa 6: o mesmo áudio nunca é gerado duas vezes.
    assert len(speech.calls) == 1


def test_same_text_in_another_document_reuses_the_audio(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    # Outro ficheiro (título diferente, logo outro hash) com o mesmo texto.
    twin = upload(client, make_epub(title="Outra edição"))

    request_audio(client, block_id_of(client, book["id"]))
    response = request_audio(client, block_id_of(client, twin["id"]))

    assert response.json()["cached"] is True
    assert len(speech.calls) == 1


def test_changing_the_language_changes_the_voice_and_generates_new_audio(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    block_id = block_id_of(client, book["id"])
    english = request_audio(client, block_id).json()

    client.patch(f"/api/v1/documents/{book['id']}", json={"language": "fr"})
    french = request_audio(client, block_id).json()

    assert french["voice"] == "fake-fr"
    assert french["cached"] is False
    assert french["audio_url"] != english["audio_url"]
    assert len(speech.calls) == 2


def test_simultaneous_requests_for_one_block_synthesize_once(
    app: FastAPI, client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    block_id = block_id_of(client, book["id"])
    # Síntese lenta, para os dois pedidos se cruzarem de certeza.
    speech.delay_seconds = 0.2

    def ask() -> bool:
        with app.state.session_factory() as session:
            result = get_block_audio(
                session, app.state.storage, speech, app.state.settings, block_id
            )
            return result.cached

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(ask), pool.submit(ask)]]

    assert sorted(results) == [False, True]
    assert len(speech.calls) == 1


def test_unknown_block_is_404(client: TestClient, speech: RecordingSynthesizer) -> None:
    response = request_audio(client, 999)

    assert response.status_code == 404
    assert response.json()["code"] == "block_not_found"


def test_document_without_language_cannot_be_synthesized(
    client: TestClient, speech: RecordingSynthesizer
) -> None:
    # Só algarismos e sem língua declarada: não há como detetar a língua.
    document = upload(client, make_epub({"c.xhtml": "<p>1865 1866 1867.</p>"}, language=None))
    assert document["language"] is None

    response = request_audio(client, block_id_of(client, document["id"]))

    assert response.status_code == 422
    assert response.json()["code"] == "language_required"
    assert speech.calls == []


def test_provider_failure_is_reported_and_nothing_is_cached(
    client: TestClient, speech: RecordingSynthesizer, book: dict, settings: Settings
) -> None:
    block_id = block_id_of(client, book["id"])
    speech.fail = True

    failed = request_audio(client, block_id)

    assert failed.status_code == 502
    assert failed.headers["content-type"] == PROBLEM_JSON
    assert failed.json()["code"] == "tts_provider_error"
    assert not (settings.data_dir / "files" / "audio").exists()
    assert client.get("/api/v1/usage").json()["tts"]["requests"] == 0

    # Quando o serviço volta, o mesmo pedido funciona e gera o áudio.
    speech.fail = False
    assert request_audio(client, block_id).json()["cached"] is False


def test_synthesis_is_logged_without_the_text(
    client: TestClient, speech: RecordingSynthesizer, book: dict, settings: Settings
) -> None:
    request_audio(client, block_id_of(client, book["id"]))

    for handler in logging.getLogger().handlers:
        handler.flush()
    log = (settings.log_dir / "app.log").read_text(encoding="utf-8")

    assert "audio_synthesized" in log
    assert "cat sat" not in log


# --- Documentos privados ----------------------------------------------------


def test_private_document_needs_confirmation_before_text_leaves(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    client.patch(f"/api/v1/documents/{book['id']}", json={"is_private": True})
    block_id = block_id_of(client, book["id"])

    refused = request_audio(client, block_id)

    assert refused.status_code == 409
    assert refused.json()["code"] == "private_document_confirmation_required"
    assert refused.json()["characters"] > 0
    assert speech.calls == []

    confirmed = request_audio(client, block_id, confirm_private=True)
    assert confirmed.status_code == 200
    assert len(speech.calls) == 1


def test_cached_audio_of_a_private_document_needs_no_confirmation(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    block_id = block_id_of(client, book["id"])
    request_audio(client, block_id)
    client.patch(f"/api/v1/documents/{book['id']}", json={"is_private": True})

    # O áudio já existe: nada sai do portátil, por isso não há o que confirmar.
    response = request_audio(client, block_id)

    assert response.status_code == 200
    assert response.json()["cached"] is True


# --- Teto mensal e consumo --------------------------------------------------


def test_monthly_limit_blocks_new_synthesis_but_not_cached_audio(
    app: FastAPI, client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    first_block = block_id_of(client, book["id"], chapter=0)
    second_block = block_id_of(client, book["id"], chapter=1)
    request_audio(client, first_block)
    # Baixa o teto para um valor já ultrapassado pelo que foi sintetizado.
    app.state.settings.monthly_tts_char_limit = 10

    refused = request_audio(client, second_block)

    assert refused.status_code == 429
    assert refused.headers["content-type"] == PROBLEM_JSON
    body = refused.json()
    assert body["code"] == "tts_quota_exceeded"
    assert body["monthly_character_limit"] == 10
    assert body["characters_used"] > 10
    assert len(speech.calls) == 1
    # O que já estava em cache continua a tocar.
    assert request_audio(client, first_block).status_code == 200


def test_usage_reports_synthesis_cache_hits_and_estimated_cost(
    client: TestClient, speech: RecordingSynthesizer, book: dict, settings: Settings
) -> None:
    block = blocks_of(client, book["id"])[0]
    characters = len(block["text"])
    request_audio(client, block["id"])
    request_audio(client, block["id"])

    usage = client.get("/api/v1/usage").json()

    assert len(usage["month"]) == 7 and usage["month"][4] == "-"
    tts = usage["tts"]
    assert tts["requests"] == 2
    assert tts["cache_hits"] == 1
    assert tts["cache_hit_rate"] == 0.5
    assert tts["characters_synthesized"] == characters
    assert tts["characters_from_cache"] == characters
    # Só a síntese conta para o custo; o acerto de cache é gratuito.
    assert tts["estimated_cost_usd"] == pytest.approx(characters * 16 / 1_000_000)
    assert tts["monthly_character_limit"] == settings.monthly_tts_char_limit
    assert tts["characters_remaining"] == settings.monthly_tts_char_limit - characters


def test_usage_starts_empty(client: TestClient) -> None:
    tts = client.get("/api/v1/usage").json()["tts"]

    assert tts["requests"] == 0
    assert tts["cache_hit_rate"] is None
    assert tts["estimated_cost_usd"] == 0


# --- Estimativa -------------------------------------------------------------


def estimate(client: TestClient, document_id: int, **body: object):
    return client.post(f"/api/v1/documents/{document_id}/audio/estimate", json=body or None)


def test_estimate_counts_characters_and_what_is_already_cached(
    client: TestClient, speech: RecordingSynthesizer, book: dict
) -> None:
    first, second = (blocks_of(client, book["id"], chapter)[0] for chapter in (0, 1))
    total = len(first["text"]) + len(second["text"])

    before = estimate(client, book["id"]).json()
    request_audio(client, first["id"])
    after = estimate(client, book["id"]).json()

    assert before["blocks_total"] == 2
    assert before["blocks_cached"] == 0
    assert before["characters_total"] == total
    assert before["characters_to_synthesize"] == total
    assert before["estimated_cost_usd"] == pytest.approx(total * 16 / 1_000_000)
    assert before["exceeds_monthly_limit"] is False

    assert after["blocks_cached"] == 1
    assert after["characters_cached"] == len(first["text"])
    assert after["characters_to_synthesize"] == len(second["text"])
    assert after["characters_used_this_month"] == len(first["text"])
    # Estimar não gera áudio: só houve a síntese pedida explicitamente.
    assert len(speech.calls) == 1


def test_estimate_can_be_limited_to_one_chapter(client: TestClient, book: dict) -> None:
    second = blocks_of(client, book["id"], chapter=1)[0]

    body = estimate(client, book["id"], chapter_position=1).json()

    assert body["blocks_total"] == 1
    assert body["characters_total"] == len(second["text"])


def test_estimate_warns_when_it_would_pass_the_monthly_limit(
    app: FastAPI, client: TestClient, book: dict
) -> None:
    app.state.settings.monthly_tts_char_limit = 10

    assert estimate(client, book["id"]).json()["exceeds_monthly_limit"] is True


def test_estimate_errors(client: TestClient, book: dict) -> None:
    unknown_document = estimate(client, 999)
    unknown_chapter = estimate(client, book["id"], chapter_position=42)

    assert (unknown_document.status_code, unknown_document.json()["code"]) == (
        404,
        "document_not_found",
    )
    assert (unknown_chapter.status_code, unknown_chapter.json()["code"]) == (
        404,
        "chapter_not_found",
    )


# --- Ficheiro de áudio ------------------------------------------------------


@pytest.fixture
def audio_url(client: TestClient, speech: RecordingSynthesizer, book: dict) -> str:
    return request_audio(client, block_id_of(client, book["id"])).json()["audio_url"]


def test_audio_file_is_served_and_can_be_cached_forever(client: TestClient, audio_url: str) -> None:
    response = client.get(audio_url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["accept-ranges"] == "bytes"
    assert "immutable" in response.headers["cache-control"]
    # É um ficheiro WAV válido.
    with wave.open(io.BytesIO(response.content)) as wav_file:
        assert wav_file.getnframes() > 0


def test_audio_file_supports_partial_requests(client: TestClient, audio_url: str) -> None:
    whole = client.get(audio_url).content

    first = client.get(audio_url, headers={"Range": "bytes=0-99"})
    rest = client.get(audio_url, headers={"Range": "bytes=100-"})
    tail = client.get(audio_url, headers={"Range": "bytes=-10"})

    assert first.status_code == rest.status_code == tail.status_code == 206
    assert first.headers["content-range"] == f"bytes 0-99/{len(whole)}"
    assert first.content + rest.content == whole
    assert tail.content == whole[-10:]


def test_range_past_the_end_is_rejected(client: TestClient, audio_url: str) -> None:
    response = client.get(audio_url, headers={"Range": "bytes=99999999-"})

    assert response.status_code == 416
    assert response.json()["code"] == "range_not_satisfiable"


@pytest.mark.parametrize("name", ["0" * 64, "nao-e-um-hash", "..%2F..%2Fetc%2Fpasswd"])
def test_unknown_or_malformed_audio_name_is_404(client: TestClient, name: str) -> None:
    response = client.get(f"/api/v1/audio/{name}")

    assert response.status_code == 404


# --- Apagar documentos ------------------------------------------------------


def audio_files(settings: Settings) -> list[str]:
    folder = settings.data_dir / "files" / "audio"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


def test_deleting_a_document_deletes_its_audio(
    client: TestClient, speech: RecordingSynthesizer, book: dict, settings: Settings
) -> None:
    url = request_audio(client, block_id_of(client, book["id"])).json()["audio_url"]
    assert len(audio_files(settings)) == 1

    client.delete(f"/api/v1/documents/{book['id']}")

    assert audio_files(settings) == []
    assert client.get(url).status_code == 404
    # O registo do que foi gasto mantém-se depois de apagar o documento.
    assert client.get("/api/v1/usage").json()["tts"]["requests"] == 1


def test_audio_shared_with_another_document_is_kept(
    client: TestClient, speech: RecordingSynthesizer, book: dict, settings: Settings
) -> None:
    twin = upload(client, make_epub(title="Outra edição"))
    request_audio(client, block_id_of(client, book["id"]))
    url = request_audio(client, block_id_of(client, twin["id"])).json()["audio_url"]

    client.delete(f"/api/v1/documents/{book['id']}")

    assert len(audio_files(settings)) == 1
    assert client.get(url).status_code == 200


# --- Chave de cache (ADR-004) -----------------------------------------------


def test_cache_key_is_stable_and_depends_on_text_voice_and_cleaning_version() -> None:
    key = audio_cache_key("The cat sat.", "fake-en", 1)

    assert key == audio_cache_key("The cat sat.", "fake-en", 1)
    assert len(key) == 64
    assert key != audio_cache_key("The cat sat!", "fake-en", 1)
    assert key != audio_cache_key("The cat sat.", "fake-fr", 1)
    assert key != audio_cache_key("The cat sat.", "fake-en", 2)


def test_cache_key_does_not_confuse_where_the_text_ends() -> None:
    # Se as partes fossem simplesmente coladas, estes dois casos dariam o mesmo.
    assert audio_cache_key("ab", "c", 1) != audio_cache_key("a", "bc", 1)


# --- Alinhamento (ADR-003) --------------------------------------------------


def timing(offset: int, length: int, start_ms: int, end_ms: int) -> WordTiming:
    return WordTiming(offset, length, start_ms, end_ms)


def test_alignment_matches_by_position_when_punctuation_is_attached() -> None:
    #        0123456789012
    text = "The cat sat."
    words = [(0, 3), (4, 7), (8, 11)]
    # O serviço devolve "sat." com o ponto; a nossa palavra é "sat".
    timings = [timing(0, 3, 0, 200), timing(4, 3, 250, 500), timing(8, 4, 550, 900)]

    aligned = align_timings(words, timings)

    assert text[8:11] == "sat"
    # "sat" ocupa três dos quatro caracteres de "sat.", por isso fica com
    # três quartos do intervalo desse tempo.
    assert aligned == [
        TimedWord(0, 3, 0, 200),
        TimedWord(4, 7, 250, 500),
        TimedWord(8, 11, 550, 812),
    ]


def test_alignment_merges_several_timings_into_one_word() -> None:
    # "rabbit-hole" é uma palavra nossa, mas o serviço diz-a em dois tempos.
    words = [(0, 11)]
    timings = [timing(0, 6, 100, 400), timing(7, 4, 420, 700)]

    assert align_timings(words, timings) == [TimedWord(0, 11, 100, 700)]


def test_alignment_splits_one_timing_between_the_words_it_covers() -> None:
    # O serviço trata "New York" como uma só unidade de 600 ms. Cada palavra
    # fica com a parte que lhe corresponde, pela posição no texto.
    words = [(0, 3), (4, 8)]
    timings = [timing(0, 8, 0, 600)]

    assert align_timings(words, timings) == [TimedWord(0, 3, 0, 225), TimedWord(4, 8, 300, 600)]


def test_words_sharing_a_timing_are_highlighted_in_reading_order() -> None:
    # Caso real do Azure: "las 8:30 p. m." chega como um só tempo.
    text = "las 8:30 p. m."
    words = [(0, 3), (4, 5), (6, 8), (9, 10), (12, 13)]
    timings = [timing(0, len(text), 1000, 2400)]

    aligned = align_timings(words, timings)

    starts = [word.start_ms for word in aligned]
    assert starts == sorted(set(starts))
    assert aligned[0].start_ms == 1000
    assert aligned[-1].end_ms <= 2400


def test_word_without_any_timing_gets_none() -> None:
    words = [(0, 3), (4, 7), (8, 11)]
    timings = [timing(0, 3, 0, 200), timing(8, 3, 500, 700)]

    aligned = align_timings(words, timings)

    assert aligned[1] == TimedWord(4, 7, None, None)
    assert aligned[2] == TimedWord(8, 11, 500, 700)


def test_alignment_ignores_timings_for_text_that_is_not_a_word() -> None:
    # Um tempo para um travessão isolado não pertence a nenhuma palavra.
    words = [(0, 3), (6, 9)]
    timings = [timing(0, 3, 0, 200), timing(4, 1, 210, 260), timing(6, 3, 300, 500)]

    assert align_timings(words, timings) == [TimedWord(0, 3, 0, 200), TimedWord(6, 9, 300, 500)]


# --- Simulador --------------------------------------------------------------


def test_fake_synthesizer_times_point_at_the_text() -> None:
    text = "One two.\nThree!"

    result = FakeSpeechSynthesizer().synthesize(text, "fake-en")

    pieces = [text[t.text_offset : t.text_offset + t.length] for t in result.timings]
    assert pieces == ["One", "two.", "Three!"]
    for previous, current in zip(result.timings, result.timings[1:], strict=False):
        assert previous.end_ms <= current.start_ms
    assert result.timings[-1].end_ms <= result.duration_ms
    # O ficheiro tem a duração anunciada.
    with wave.open(io.BytesIO(result.audio)) as wav_file:
        seconds = wav_file.getnframes() / wav_file.getframerate()
    assert seconds * 1000 == pytest.approx(result.duration_ms, abs=1)


# --- Estado do serviço de voz no /health ------------------------------------


def test_health_is_degraded_after_a_voice_failure_and_recovers(
    app: FastAPI, client: TestClient, book: dict
) -> None:
    # Aqui usamos o fornecedor tal como a aplicação o monta, embrulhado pelo
    # TrackedSynthesizer, e trocamos só o fornecedor de dentro.
    inner = RecordingSynthesizer()
    app.state.speech = TrackedSynthesizer(inner)
    block_id = block_id_of(client, book["id"])

    inner.fail = True
    assert request_audio(client, block_id).status_code == 502
    degraded = client.get("/api/v1/health")

    # O sistema continua a responder 200: ler e ouvir o que está em cache funciona.
    assert degraded.status_code == 200
    assert degraded.json()["status"] == "degraded"
    assert degraded.json()["checks"]["speech"] == "error"
    assert degraded.json()["checks"]["database"] == "ok"

    inner.fail = False
    assert request_audio(client, block_id).status_code == 200
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_old_voice_failures_stop_counting(app: FastAPI, client: TestClient) -> None:
    tracked = TrackedSynthesizer(RecordingSynthesizer())
    tracked.last_failure_at = datetime.now(UTC) - timedelta(minutes=11)
    app.state.speech = tracked

    assert client.get("/api/v1/health").json()["status"] == "ok"
