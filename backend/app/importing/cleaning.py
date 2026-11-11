"""Limpeza do texto extraído dos documentos."""

import re
import unicodedata

# Sobe este número sempre que a limpeza passar a produzir texto diferente.
# A versão entra na chave de cache do áudio (ADR-004): o áudio gerado com uma
# versão antiga deixa de ser reutilizado, sem ser preciso apagar nada.
CLEANING_VERSION = 1

# Caracteres invisíveis que os livros trazem e que só atrapalham: hífen
# opcional (U+00AD), espaços de largura zero (U+200B a U+200D), "word joiner"
# (U+2060) e a marca de ordem de bytes (U+FEFF).
_INVISIBLE_CHARS = re.compile("[­​‌‍⁠﻿]")

# \s apanha espaços, tabulações, quebras de linha e também os espaços
# especiais do Unicode, como o espaço não separável (U+00A0).
_WHITESPACE_RUN = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Normaliza um pedaço de texto: uma só forma Unicode e espaços simples."""
    # Em Unicode, "é" pode ser um carácter ou dois ("e" seguido de acento).
    # A forma NFC junta-os num só, para o mesmo texto dar sempre a mesma
    # sequência de caracteres (e portanto as mesmas posições e o mesmo hash).
    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE_CHARS.sub("", text)
    return _WHITESPACE_RUN.sub(" ", text).strip()
