"""Importação de um documento, do ficheiro recebido às linhas na base de dados."""

import hashlib
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importing.cleaning import CLEANING_VERSION
from app.importing.epub import parse_epub
from app.importing.language import detect_language, take_sample
from app.importing.models import Block, Chapter, Document, Sentence
from app.importing.segmentation import build_blocks
from app.importing.validation import invalid_epub, validate_file_size
from app.storage.base import FileStorage

logger = logging.getLogger(__name__)

UNTITLED = "Sem título"


@dataclass(frozen=True)
class ImportResult:
    document: Document
    # False quando o ficheiro já tinha sido importado e devolvemos o existente.
    created: bool


def import_epub(session: Session, storage: FileStorage, data: bytes) -> ImportResult:
    """Importa um EPUB: valida, extrai o texto, segmenta e guarda tudo.

    Não faz nenhuma chamada externa; nada sai do portátil neste passo.
    Lança ProblemError se o ficheiro for recusado.
    """
    started_at = time.perf_counter()
    validate_file_size(len(data))

    # O hash identifica o conteúdo do ficheiro, seja qual for o nome que traz.
    # Importar o mesmo livro outra vez devolve o documento que já existe, e o
    # áudio e as respostas do tutor já gerados continuam a servir (ADR-004).
    file_hash = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(Document).where(Document.file_hash == file_hash))
    if existing is not None:
        logger.info("document_already_imported", extra={"document_id": existing.id})
        return ImportResult(document=existing, created=False)

    content = parse_epub(data)
    if not content.chapters:
        raise invalid_epub("O EPUB não tem texto que se possa ler.")

    all_paragraphs = [paragraph for chapter in content.chapters for paragraph in chapter.paragraphs]
    language = detect_language(take_sample(all_paragraphs), content.declared_language)

    storage_key = f"originals/{file_hash}.epub"
    document = Document(
        # Os metadados vêm do ficheiro e podem ser enormes; as colunas têm limite.
        title=(content.title or UNTITLED)[:500],
        author=content.author[:500] if content.author else None,
        language=language,
        format="epub",
        file_hash=file_hash,
        file_size=len(data),
        storage_key=storage_key,
        cleaning_version=CLEANING_VERSION,
    )
    for chapter_position, raw_chapter in enumerate(content.chapters):
        chapter = Chapter(
            position=chapter_position,
            title=raw_chapter.title[:500] if raw_chapter.title else None,
        )
        for block_position, block_data in enumerate(build_blocks(raw_chapter.paragraphs, language)):
            block = Block(
                position=block_position,
                text=block_data.text,
                char_count=len(block_data.text),
            )
            block.sentences = [
                Sentence(
                    position=sentence_position,
                    text=sentence.text,
                    start_offset=sentence.start,
                    end_offset=sentence.end,
                    words=[list(word) for word in sentence.words],
                )
                for sentence_position, sentence in enumerate(block_data.sentences)
            ]
            chapter.blocks.append(block)
        document.chapters.append(chapter)

    # Primeiro o ficheiro, depois a base de dados. Se o commit falhar fica um
    # ficheiro a mais no disco, o que é inofensivo; a ordem inversa podia
    # deixar um documento registado sem o seu original.
    storage.save(storage_key, data)
    # Basta adicionar o documento: o ORM grava capítulos, blocos e frases por
    # arrasto, numa única transação. Ou fica tudo gravado, ou nada.
    session.add(document)
    session.commit()

    # Só identificadores, contagens e tempos; nunca o título nem o texto (regra fixa 9).
    logger.info(
        "document_imported",
        extra={
            "document_id": document.id,
            "file_size": len(data),
            "language": language,
            "chapters": len(document.chapters),
            "characters": sum(len(paragraph) for paragraph in all_paragraphs),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
        },
    )
    return ImportResult(document=document, created=True)
