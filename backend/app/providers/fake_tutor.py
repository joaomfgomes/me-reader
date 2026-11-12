"""Tutor simulado: responde no formato certo, sem modelo nenhum por trás.

Serve para os testes (regra fixa 5: nenhum teste faz chamadas pagas) e para
desenvolver a interface sem gastar dinheiro. As "explicações" dizem
claramente que são simuladas, para ninguém as tomar por verdadeiras.
"""

import json
import re

from pydantic import BaseModel

from app.tutor.tutor import TutorReply

_WORD_TAG = re.compile(r"<palavra>(.*?)</palavra>", re.DOTALL)


class FakeTutor:
    """Implementação de Tutor que não faz chamadas externas."""

    name = "fake"
    model = "fake-tutor-1"

    def explain_word(
        self, system_prompt: str, user_message: str, response_model: type[BaseModel]
    ) -> TutorReply:
        match = _WORD_TAG.search(user_message)
        word = match.group(1).strip() if match else "?"
        reply = {
            "lemma": word.lower(),
            "part_of_speech": "classe por determinar (tutor simulado)",
            "translation": f"[tradução simulada de «{word}»]",
            "definition": (
                "Explicação simulada. Configura um fornecedor de LLM para veres "
                "uma explicação verdadeira desta palavra."
            ),
            "pronunciation": word.lower(),
            "ipa": f"/{word.lower()}/",
        }
        text = json.dumps(reply, ensure_ascii=False)
        # Uma estimativa grosseira (um token por cada quatro caracteres), só
        # para a página de custos ter números com que trabalhar.
        return TutorReply(
            text=text,
            input_tokens=(len(system_prompt) + len(user_message)) // 4,
            output_tokens=len(text) // 4,
        )
