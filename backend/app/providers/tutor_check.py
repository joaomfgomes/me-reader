"""Verificação manual do tutor configurado: "make tutor-check".

Pede a explicação de uma palavra por língua e mostra o resultado, para se
poder julgar a qualidade das explicações em português de Portugal. Com a
Anthropic faz cinco chamadas verdadeiras, que custam uma fração de cêntimo.

Não faz parte dos testes automáticos, que nunca fazem chamadas pagas (regra
fixa 5). As frases foram escritas para este fim; não vêm de nenhum documento.
"""

import sys

from pydantic import ValidationError

from app.core.config import Settings
from app.providers import create_tutor
from app.tutor.prompts import WORD_PROMPT_VERSION, load_prompt
from app.tutor.service import build_word_message
from app.tutor.tutor import TutorProviderError, WordExplanation
from app.usage.service import estimate_llm_cost

# (língua, frase, palavra): cada palavra tem um sentido que depende da frase.
CASES = [
    ("en", "She ran out of patience and gave up on the whole plan.", "gave"),
    ("es", "Al final se dio cuenta de que había dejado las llaves dentro.", "cuenta"),
    ("fr", "Il a fini par se rendre compte qu'il s'était trompé de quai.", "quai"),
    ("de", "Er hat sich gestern beim Aufräumen den Kopf an der Tür gestoßen.", "gestoßen"),
    ("it", "Non me ne ero accorto finché lei non me l'ha fatto notare.", "accorto"),
]


def main() -> int:
    settings = Settings()
    tutor = create_tutor(settings)
    system_prompt = load_prompt("word", WORD_PROMPT_VERSION)
    print(f"Fornecedor: {tutor.name}  modelo: {tutor.model}  prompt: v{WORD_PROMPT_VERSION}")
    failures = 0
    total_cost = 0.0

    for language, sentence, word in CASES:
        message = build_word_message(word, sentence, None, None, language)
        print(f"\n[{language}] «{word}» em: {sentence}")
        try:
            reply = tutor.explain_word(system_prompt, message, WordExplanation)
        except TutorProviderError as exc:
            print(f"  FALHOU: {exc}")
            failures += 1
            continue

        cost = estimate_llm_cost(reply.input_tokens, reply.output_tokens, settings)
        total_cost += cost
        try:
            explanation = WordExplanation.model_validate_json(reply.text)
        except ValidationError as exc:
            print(f"  RESPOSTA INVÁLIDA ({exc.error_count()} erro(s))")
            failures += 1
            continue

        for field, value in explanation.model_dump().items():
            print(f"  {field:15} {value}")
        print(f"  tokens: {reply.input_tokens} de entrada, {reply.output_tokens} de saída")

    print(f"\nCusto estimado: {total_cost:.6f} USD")
    print("Tudo certo." if failures == 0 else f"{failures} caso(s) com problemas.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
