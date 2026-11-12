"""Prompts do tutor, em ficheiros com número de versão (ADR-005).

Cada prompt vive num ficheiro "<nome>_v<versão>.md". Para o alterar, cria-se
um ficheiro novo com a versão seguinte e sobe-se a constante correspondente.
A versão entra na chave de cache das respostas: um prompt novo gera respostas
novas e as antigas ficam guardadas, sem serem reutilizadas nem apagadas.
"""

from functools import lru_cache
from pathlib import Path

WORD_PROMPT_VERSION = 1

_PROMPTS_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str, version: int) -> str:
    """Lê o texto de um prompt. O resultado fica em memória depois da primeira leitura."""
    return (_PROMPTS_DIR / f"{name}_v{version}.md").read_text(encoding="utf-8").strip()
