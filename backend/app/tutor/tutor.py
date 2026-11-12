"""Interface do tutor: o que a aplicação precisa de um modelo de linguagem.

O resto da app só conhece este ficheiro. As implementações concretas (o
simulador e a Anthropic) vivem em app/providers/ e podem
ser trocadas sem mexer em mais nada (ADR-005).
"""

from dataclasses import dataclass
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints

# Texto obrigatório, sem espaços à volta e com um tamanho máximo. Os limites
# impedem que uma resposta desgovernada do modelo encha o ecrã ou a base de dados.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)]


class WordExplanation(BaseModel):
    """A explicação de uma palavra no contexto de uma frase.

    É o formato fixo que a interface mostra. Qualquer resposta do modelo é
    validada contra este esquema; o que não passar nunca chega ao ecrã nem à
    cache (ADR-005).
    """

    # extra="forbid": campos que não pedimos tornam a resposta inválida.
    model_config = ConfigDict(extra="forbid")

    # Forma de dicionário, na língua do texto ("went" tem o lema "go").
    lemma: ShortText
    # Classe gramatical, em português.
    part_of_speech: ShortText
    # Tradução para pt-PT do sentido que a palavra tem nesta frase.
    translation: ShortText
    # Explicação curta, em pt-PT, do sentido nesta frase.
    definition: LongText
    # Pronúncia aproximada, escrita para um leitor português.
    pronunciation: ShortText
    # Transcrição no Alfabeto Fonético Internacional.
    ipa: ShortText


@dataclass(frozen=True)
class TutorReply:
    """Resposta em bruto do modelo, antes de ser validada."""

    text: str
    # Tokens gastos, para o registo de consumo. Um token é um pedaço de
    # palavra; é a unidade em que os modelos são faturados.
    input_tokens: int
    output_tokens: int


class TutorProviderError(Exception):
    """O serviço do modelo falhou ou está indisponível."""


class Tutor(Protocol):
    # Nome do fornecedor ("fake", "anthropic") e do modelo. O modelo entra na
    # chave de cache: mudar de modelo gera respostas novas.
    name: str
    model: str

    def explain_word(
        self, system_prompt: str, user_message: str, response_model: type[BaseModel]
    ) -> TutorReply:
        """Pede a explicação de uma palavra.

        Recebe o prompt já montado e o esquema da resposta esperada, para o
        fornecedor poder pedir ao modelo uma saída nesse formato. Devolve o
        texto tal como veio: validar é trabalho de quem chama. Lança
        TutorProviderError se o serviço falhar.

        O ADR-005 prevê um método por tipo de pedido; os restantes (traduzir,
        gramática, expressão, simplificar) entram na Fase 4.
        """
        ...
