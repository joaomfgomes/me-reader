"""Divisão do texto em blocos, frases e palavras, com posições.

Todas as posições são índices de caracteres dentro do texto do bloco:
block.text[start:end] devolve a frase ou a palavra. O bloco é a unidade de
síntese de áudio, e na Fase 2 o serviço de voz vai devolver os tempos de cada
palavra por posição no texto enviado. Ter tudo nas coordenadas do bloco é o que
vai permitir ligar um tempo a uma palavra (ADR-003).
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import pysbd

# Tamanho que tentamos dar a cada bloco. Um bloco junta parágrafos inteiros
# até chegar perto deste valor; um parágrafo nunca é partido a meio.
TARGET_BLOCK_CHARS = 1500

# Língua usada para dividir frases quando a do documento é desconhecida.
FALLBACK_LANGUAGE = "en"

# Uma palavra: letras ou algarismos, podendo ter apóstrofos ou hífenes no meio
# ("don't", "rabbit-hole", "aujourd'hui"). [^\W_] quer dizer "carácter de
# palavra, exceto o sublinhado" e funciona com letras acentuadas.
_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


@dataclass(frozen=True)
class SentenceData:
    text: str
    start: int
    end: int
    # Pares (início, fim) de cada palavra, nas coordenadas do bloco.
    words: list[tuple[int, int]]


@dataclass(frozen=True)
class BlockData:
    # Parágrafos separados por "\n".
    text: str
    sentences: list[SentenceData]


def build_blocks(paragraphs: list[str], language: str | None) -> list[BlockData]:
    """Agrupa parágrafos em blocos e divide cada bloco em frases e palavras."""
    segmenter = _get_segmenter(language or FALLBACK_LANGUAGE)

    blocks: list[BlockData] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        if current and current_size + len(paragraph) > TARGET_BLOCK_CHARS:
            blocks.append(_make_block(current, segmenter))
            current, current_size = [], 0
        current.append(paragraph)
        current_size += len(paragraph) + 1
    if current:
        blocks.append(_make_block(current, segmenter))
    return blocks


@lru_cache(maxsize=8)
def _get_segmenter(language: str) -> pysbd.Segmenter:
    # O pySBD divide frases com regras por língua. Sabe, por exemplo, que o
    # ponto de "Mr." ou de "p. ej." não acaba a frase.
    # lru_cache guarda o resultado: só se cria um segmentador por língua.
    return pysbd.Segmenter(language=language, clean=False)


def _make_block(paragraphs: list[str], segmenter: pysbd.Segmenter) -> BlockData:
    text = "\n".join(paragraphs)
    sentences: list[SentenceData] = []
    offset = 0
    # As frases são procuradas parágrafo a parágrafo, por isso uma frase nunca
    # atravessa uma quebra de parágrafo.
    for paragraph in paragraphs:
        for start, end in _sentence_spans(paragraph, segmenter):
            block_start, block_end = offset + start, offset + end
            sentence_text = text[block_start:block_end]
            words = [
                (block_start + match.start(), block_start + match.end())
                for match in _WORD.finditer(sentence_text)
            ]
            sentences.append(SentenceData(sentence_text, block_start, block_end, words))
        offset += len(paragraph) + 1  # +1 pelo "\n" que separa os parágrafos
    return BlockData(text=text, sentences=sentences)


def _sentence_spans(paragraph: str, segmenter: pysbd.Segmenter) -> list[tuple[int, int]]:
    """Posições (início, fim) de cada frase dentro do parágrafo."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for piece in segmenter.segment(paragraph):
        sentence = piece.strip()
        if not sentence:
            continue
        # O pySBD devolve o texto de cada frase, mas não onde ela está.
        # Procuramo-la a partir do fim da frase anterior.
        start = paragraph.find(sentence, cursor)
        # Entre duas frases só pode haver espaços. Se não encontrarmos a frase,
        # ou se ficar texto por cobrir, o pySBD alterou alguma coisa e as
        # posições deixaram de ser fiáveis: tratamos o parágrafo como uma frase.
        if start == -1 or paragraph[cursor:start].strip():
            return [(0, len(paragraph))]
        cursor = start + len(sentence)
        spans.append((start, cursor))

    if not spans or paragraph[cursor:].strip():
        return [(0, len(paragraph))]
    return spans
