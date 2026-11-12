"""Tutor com os modelos Claude, da Anthropic (ADR-005).

É o único ficheiro da aplicação que conhece o SDK da Anthropic.
"""

import logging
from typing import Any

import anthropic
from pydantic import BaseModel

from app.tutor.tutor import TutorProviderError, TutorReply

logger = logging.getLogger(__name__)

# Uma explicação tem menos de 300 tokens, mas o limite inclui o raciocínio que
# o modelo faz antes de responder. Um limite curto demais cortaria a resposta
# a meio e obrigaria a pagar uma segunda chamada.
_MAX_TOKENS = 4000

# Segundos de espera por pedido. Quem carregou numa palavra não vai esperar mais.
_TIMEOUT_SECONDS = 30.0


def json_schema_for(response_model: type[BaseModel]) -> dict[str, Any]:
    """Esquema JSON mínimo de um modelo Pydantic cujos campos são todos texto.

    A API garante que a resposta cumpre o esquema enviado, mas só aceita um
    subconjunto do JSON Schema (não aceita, por exemplo, tamanhos máximos).
    Por isso enviamos só a forma, com os nomes dos campos, e deixamos as
    regras mais finas para a validação com Pydantic que a aplicação faz a
    seguir.
    """
    fields = list(response_model.model_fields)
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in fields},
        "required": fields,
        "additionalProperties": False,
    }


class AnthropicTutor:
    """Implementação de Tutor com a API de mensagens da Anthropic."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self.model = model
        # O SDK repete sozinho os pedidos que falham por erros passageiros
        # (rede, limite de pedidos, erro do servidor), duas vezes por omissão.
        # Os testes passam um cliente a fingir no parâmetro "client".
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=_TIMEOUT_SECONDS)

    def explain_word(
        self, system_prompt: str, user_message: str, response_model: type[BaseModel]
    ) -> TutorReply:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                # As instruções vão em "system" e o texto do livro na mensagem
                # do utilizador: o modelo dá mais peso às primeiras.
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                output_config={
                    # Explicar uma palavra é uma tarefa curta: esforço baixo
                    # responde mais depressa e gasta menos tokens.
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": json_schema_for(response_model)},
                },
            )
        # Do erro mais específico para o mais geral. Em todos os casos só
        # registamos o tipo de erro: a mensagem pode trazer partes do pedido.
        except anthropic.AuthenticationError as exc:
            raise self._failure("authentication_error") from exc
        except anthropic.RateLimitError as exc:
            raise self._failure("rate_limit_error") from exc
        except anthropic.APIStatusError as exc:
            raise self._failure(f"http_{exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            # Inclui os pedidos que excederam o tempo de espera.
            raise self._failure("connection_error") from exc

        # O modelo pode recusar um pedido por razões de segurança. Nesse caso
        # a resposta vem sem o JSON pedido, e não vale a pena tentar outra vez.
        if response.stop_reason == "refusal":
            raise self._failure("refusal")

        # A resposta é uma lista de blocos; o raciocínio do modelo vem em
        # blocos próprios. O JSON está no bloco de texto.
        text = next((block.text for block in response.content if block.type == "text"), "")
        return TutorReply(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def _failure(self, reason: str) -> TutorProviderError:
        logger.warning("anthropic_tutor_failed", extra={"reason": reason, "model": self.model})
        return TutorProviderError(f"anthropic: {reason}")
