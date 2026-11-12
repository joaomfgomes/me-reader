"""Testes do tutor da Anthropic, sem falar com a Anthropic.

A chamada à API é substituída por um cliente a fingir, com a mesma forma do
verdadeiro. Os erros são os do SDK, construídos à mão.
"""

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.core.config import Settings
from app.providers import create_tutor
from app.providers.anthropic_tutor import AnthropicTutor, json_schema_for
from app.tutor.tutor import TutorProviderError, WordExplanation

GOOD = {
    "lemma": "fall",
    "part_of_speech": "verbo irregular, passado simples",
    "translation": "caiu",
    "definition": "Passado de «fall» (cair).",
    "pronunciation": "FÉL",
    "ipa": "/fɛl/",
}


def response(
    text: str = "", stop_reason: str = "end_turn", thinking: bool = True
) -> SimpleNamespace:
    """Uma resposta com a forma da do SDK: blocos de conteúdo e contagem de tokens."""
    content = [SimpleNamespace(type="thinking", thinking="")] if thinking else []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=512, output_tokens=140),
    )


class FakeClient:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def tutor_with(result: object) -> tuple[AnthropicTutor, FakeClient]:
    client = FakeClient(result)
    return AnthropicTutor("chave-de-teste", "claude-haiku-5-5", client=client), client


def status_error(cls: type, status: int) -> Exception:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    http_response = httpx2.Response(status, request=request)
    return cls("pedido com chave-de-teste e texto do livro", response=http_response, body=None)


def test_reply_carries_the_json_text_and_the_token_counts() -> None:
    tutor, _ = tutor_with(response(json.dumps(GOOD, ensure_ascii=False)))

    reply = tutor.explain_word("instruções", "mensagem", WordExplanation)

    # O texto vem do bloco de texto, não do bloco de raciocínio que o antecede.
    assert WordExplanation.model_validate_json(reply.text).lemma == "fall"
    assert (reply.input_tokens, reply.output_tokens) == (512, 140)


def test_request_separates_instructions_from_book_text_and_asks_for_the_schema() -> None:
    tutor, client = tutor_with(response(json.dumps(GOOD)))

    tutor.explain_word("instruções do tutor", "<frase>texto do livro</frase>", WordExplanation)

    (request,) = client.requests
    assert request["model"] == "claude-haiku-5-5"
    assert request["system"] == "instruções do tutor"
    assert request["messages"] == [{"role": "user", "content": "<frase>texto do livro</frase>"}]
    assert request["output_config"]["effort"] == "low"
    schema = request["output_config"]["format"]["schema"]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert schema["required"] == list(WordExplanation.model_fields)
    assert schema["additionalProperties"] is False
    # Parâmetros que os modelos atuais rejeitam não são enviados.
    assert not {"temperature", "top_p", "top_k", "thinking"} & request.keys()


def test_schema_lists_every_field_as_required_text() -> None:
    schema = json_schema_for(WordExplanation)

    assert set(schema["properties"]) == set(WordExplanation.model_fields)
    assert all(spec == {"type": "string"} for spec in schema["properties"].values())


def test_refusal_becomes_a_provider_error() -> None:
    tutor, _ = tutor_with(response(stop_reason="refusal"))

    with pytest.raises(TutorProviderError, match="refusal"):
        tutor.explain_word("instruções", "mensagem", WordExplanation)


def test_reply_without_text_is_returned_empty_for_the_service_to_reject() -> None:
    tutor, _ = tutor_with(response(text="", stop_reason="max_tokens"))

    reply = tutor.explain_word("instruções", "mensagem", WordExplanation)

    # Texto vazio não é JSON válido: o serviço trata-o como resposta inválida.
    assert reply.text == ""


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (status_error(anthropic.AuthenticationError, 401), "authentication_error"),
        (status_error(anthropic.RateLimitError, 429), "rate_limit_error"),
        (status_error(anthropic.BadRequestError, 400), "http_400"),
        (status_error(anthropic.InternalServerError, 500), "http_500"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "connection_error",
        ),
    ],
)
def test_sdk_errors_become_provider_errors_without_leaking_details(
    error: Exception, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    tutor, _ = tutor_with(error)

    with caplog.at_level("WARNING"), pytest.raises(TutorProviderError) as raised:
        tutor.explain_word("instruções", "mensagem", WordExplanation)

    assert reason in str(raised.value)
    logged = " ".join(str(record.__dict__) for record in caplog.records)
    assert reason in logged
    # Nem a chave nem o texto do pedido passam para o erro ou para os logs.
    for secret in ("chave-de-teste", "texto do livro"):
        assert secret not in str(raised.value)
        assert secret not in logged


def test_anthropic_tutor_is_created_from_the_settings() -> None:
    settings = Settings(
        _env_file=None,
        tutor_provider="anthropic",
        tutor_model="claude-haiku-5-5",
        ANTHROPIC_API_KEY="chave-de-teste",
    )

    tutor = create_tutor(settings)

    assert (tutor.name, tutor.model) == ("anthropic", "claude-haiku-5-5")
    assert "chave-de-teste" not in repr(settings)


def test_anthropic_without_a_key_refuses_to_start() -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_tutor(Settings(_env_file=None, tutor_provider="anthropic"))
