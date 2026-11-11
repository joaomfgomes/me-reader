"""Testes da importação completa, com um livro real em domínio público."""

import hashlib
import logging
import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.importing.cleaning import CLEANING_VERSION
from app.importing.models import Block, Chapter, Document, Sentence
from app.importing.service import UNTITLED, import_epub
from app.storage.disk import DiskStorage
from tests.epub_factory import make_epub


@pytest.fixture
def session(app: FastAPI) -> Iterator[Session]:
    with app.state.session_factory() as db_session:
        yield db_session


@pytest.fixture
def storage(app: FastAPI) -> DiskStorage:
    return app.state.storage


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_real_book_is_imported_with_metadata_and_chapters(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    result = import_epub(session, storage, alice_bytes)
    document = result.document

    assert result.created
    assert document.title == "Alice's Adventures in Wonderland"
    assert document.author == "Lewis Carroll"
    assert document.language == "en"
    assert document.format == "epub"
    assert document.file_size == len(alice_bytes)
    assert document.cleaning_version == CLEANING_VERSION
    assert not document.is_private

    # A página inicial do Project Gutenberg e os doze capítulos do livro.
    assert len(document.chapters) == 13
    assert [chapter.position for chapter in document.chapters] == list(range(13))
    assert document.chapters[1].title == "CHAPTER I. Down the Rabbit-Hole"
    assert document.chapters[12].title == "CHAPTER XII. Alice’s Evidence"


def test_every_sentence_and_word_position_matches_the_block_text(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    document = import_epub(session, storage, alice_bytes).document

    blocks = [block for chapter in document.chapters for block in chapter.blocks]
    sentence_total = word_total = 0
    for block in blocks:
        assert block.char_count == len(block.text)
        previous_end = 0
        for sentence in block.sentences:
            # A posição guardada aponta mesmo para a frase...
            assert block.text[sentence.start_offset : sentence.end_offset] == sentence.text
            # ...as frases vêm por ordem e não se sobrepõem...
            assert sentence.start_offset >= previous_end
            # ...e entre duas frases só há espaços ou quebras de parágrafo.
            assert block.text[previous_end : sentence.start_offset].strip() == ""
            assert "\n" not in sentence.text
            previous_end = sentence.end_offset

            for start, end in sentence.words:
                assert sentence.start_offset <= start < end <= sentence.end_offset
                assert re.fullmatch(r"[\w'’\-]+", block.text[start:end])
            sentence_total += 1
            word_total += len(sentence.words)
        assert block.text[previous_end:].strip() == ""

    # O livro tem cerca de 27 mil palavras; com a licença do Project Gutenberg
    # o ficheiro fica perto das 30 mil.
    assert len(blocks) > 100
    assert sentence_total > 1000
    assert 25_000 < word_total < 35_000


def test_imported_text_contains_no_html(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    document = import_epub(session, storage, alice_bytes).document

    for chapter in document.chapters:
        for block in chapter.blocks:
            assert not re.search(r"</?[a-zA-Z][^>]*>", block.text)


def test_known_sentence_is_found_with_its_words(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    import_epub(session, storage, alice_bytes)

    sentence = session.scalars(
        select(Sentence).where(Sentence.text == "Would the fall never come to an end?")
    ).one()
    block_text = sentence.block.text

    assert [block_text[start:end] for start, end in sentence.words] == [
        "Would", "the", "fall", "never", "come", "to", "an", "end",
    ]  # fmt: skip


def test_original_file_is_stored_under_its_hash(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    document = import_epub(session, storage, alice_bytes).document

    file_hash = hashlib.sha256(alice_bytes).hexdigest()
    assert document.file_hash == file_hash
    assert document.storage_key == f"originals/{file_hash}.epub"
    assert storage.read(document.storage_key) == alice_bytes


def test_importing_the_same_file_twice_returns_the_existing_document(
    session: Session, storage: DiskStorage, alice_bytes: bytes
) -> None:
    first = import_epub(session, storage, alice_bytes)
    sentences_after_first = count(session, Sentence)

    second = import_epub(session, storage, alice_bytes)

    assert first.created and not second.created
    assert second.document.id == first.document.id
    assert count(session, Document) == 1
    assert count(session, Sentence) == sentences_after_first


def test_deleting_a_document_removes_its_chapters_blocks_and_sentences(
    session: Session, storage: DiskStorage
) -> None:
    document = import_epub(session, storage, make_epub()).document
    assert count(session, Sentence) > 0

    session.delete(document)
    session.commit()

    assert [count(session, model) for model in (Document, Chapter, Block, Sentence)] == [0] * 4


def test_document_without_title_gets_a_placeholder(session: Session, storage: DiskStorage) -> None:
    document = import_epub(session, storage, make_epub(title=None, author=None)).document

    assert document.title == UNTITLED
    assert document.author is None


def test_epub_without_any_text_is_rejected_and_nothing_is_saved(
    session: Session, storage: DiskStorage, settings: Settings
) -> None:
    with pytest.raises(ProblemError) as error:
        import_epub(session, storage, make_epub({"cover.xhtml": "<img src='c.jpg'/>"}))

    assert error.value.code == "invalid_epub"
    assert count(session, Document) == 0
    assert not (settings.data_dir / "files").exists()


def test_rejected_file_is_not_stored(
    session: Session, storage: DiskStorage, settings: Settings
) -> None:
    with pytest.raises(ProblemError):
        import_epub(session, storage, b"isto nao e um epub")

    assert count(session, Document) == 0
    assert not (settings.data_dir / "files").exists()


def test_import_logs_counts_but_never_the_text(
    session: Session, storage: DiskStorage, settings: Settings, alice_bytes: bytes
) -> None:
    import_epub(session, storage, alice_bytes)

    for handler in logging.getLogger().handlers:
        handler.flush()
    log = (settings.log_dir / "app.log").read_text(encoding="utf-8")

    assert "document_imported" in log
    # Regra fixa 9: nem o título, nem o autor, nem o texto aparecem nos logs.
    for forbidden in ("Alice", "Carroll", "Rabbit"):
        assert forbidden not in log
