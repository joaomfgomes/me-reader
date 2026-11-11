"""Testes da divisão em blocos, frases e palavras, e da deteção de língua."""

import pytest

from app.importing import segmentation
from app.importing.language import detect_language, take_sample
from app.importing.segmentation import BlockData, build_blocks


def words_of(block: BlockData) -> list[str]:
    return [block.text[start:end] for sentence in block.sentences for start, end in sentence.words]


def test_paragraph_is_split_into_sentences() -> None:
    (block,) = build_blocks(["The cat sat. The dog barked! Did it rain?"], "en")

    assert [sentence.text for sentence in block.sentences] == [
        "The cat sat.",
        "The dog barked!",
        "Did it rain?",
    ]


def test_abbreviations_do_not_end_a_sentence() -> None:
    (block,) = build_blocks(["Mr. Smith met Dr. Jones at 5 p.m. in London. They talked."], "en")

    assert len(block.sentences) == 2


def test_offsets_point_at_the_sentence_inside_the_block() -> None:
    (block,) = build_blocks(["First one. Second one.", "Third one."], "en")

    assert block.text == "First one. Second one.\nThird one."
    for sentence in block.sentences:
        assert block.text[sentence.start : sentence.end] == sentence.text
    assert [sentence.start for sentence in block.sentences] == [0, 11, 23]


def test_sentences_never_cross_a_paragraph_break() -> None:
    # O primeiro parágrafo não acaba em ponto, mas a frase acaba com ele.
    (block,) = build_blocks(["A title without a full stop", "The text starts here."], "en")

    assert [sentence.text for sentence in block.sentences] == [
        "A title without a full stop",
        "The text starts here.",
    ]


def test_words_keep_inner_apostrophes_and_hyphens() -> None:
    (block,) = build_blocks(["“Don’t fall down the rabbit-hole,” she said—twice, in 1865!"], "en")

    assert words_of(block) == [
        "Don’t", "fall", "down", "the", "rabbit-hole", "she", "said", "twice", "in", "1865",
    ]  # fmt: skip


def test_words_with_accents_are_whole_words() -> None:
    (block,) = build_blocks(["El niño comió rápido. Größe zählt, façade aussi."], "es")

    assert words_of(block) == ["El", "niño", "comió", "rápido", "Größe", "zählt", "façade", "aussi"]


def test_paragraphs_are_grouped_into_blocks_near_the_target_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(segmentation, "TARGET_BLOCK_CHARS", 100)
    paragraphs = ["A" * 40 + ".", "B" * 40 + ".", "C" * 40 + ".", "D" * 300 + "."]

    blocks = build_blocks(paragraphs, "en")

    # Dois parágrafos cabem em 100 caracteres; o terceiro abre um bloco novo.
    # O último é maior do que o alvo e fica inteiro, sozinho.
    assert [block.text.count("\n") + 1 for block in blocks] == [2, 1, 1]
    assert "\n".join(block.text for block in blocks) == "\n".join(paragraphs)


def test_unknown_language_falls_back_to_a_default_segmenter() -> None:
    (block,) = build_blocks(["One. Two."], None)

    assert len(block.sentences) == 2


# Frases escritas para este teste, uma por língua suportada.
LANGUAGE_SAMPLES = {
    "en": "The children walked slowly through the old forest, looking for the lost dog.",
    "es": "Los niños caminaban despacio por el bosque viejo, buscando al perro perdido.",
    "fr": "Les enfants marchaient lentement dans la vieille forêt, à la recherche du chien perdu.",
    "de": "Die Kinder gingen langsam durch den alten Wald und suchten den verlorenen Hund.",
    "it": "I bambini camminavano lentamente nel vecchio bosco, cercando il cane smarrito.",
}


@pytest.mark.parametrize(("code", "text"), LANGUAGE_SAMPLES.items())
def test_language_is_detected_from_the_text(code: str, text: str) -> None:
    assert detect_language(text) == code


def test_detected_language_wins_over_a_wrong_declaration() -> None:
    assert detect_language(LANGUAGE_SAMPLES["fr"], declared="en") == "fr"


@pytest.mark.parametrize(("declared", "expected"), [("de", "de"), ("en-GB", "en"), ("it_IT", "it")])
def test_declared_language_is_used_when_the_text_is_not_enough(
    declared: str, expected: str
) -> None:
    assert detect_language("1865", declared=declared) == expected


@pytest.mark.parametrize("declared", [None, "", "pt", "xx"])
def test_language_is_unknown_without_text_or_supported_declaration(declared: str | None) -> None:
    assert detect_language("", declared=declared) is None


def test_sample_comes_from_the_middle_of_the_document() -> None:
    paragraphs = ["english licence " * 500, "texte français " * 500, "english licence " * 500]

    sample = take_sample(paragraphs)

    assert "français" in sample
    assert "english" not in sample
