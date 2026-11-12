"""Vocabulário: registar as palavras consultadas, listá-las e apagá-las."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.importing.models import Document, Sentence
from app.tutor.tutor import WordExplanation
from app.vocabulary.models import VocabularyEntry


def record_lookup(
    session: Session,
    document: Document,
    sentence: Sentence,
    word: str,
    explanation: WordExplanation,
) -> VocabularyEntry:
    """Regista a consulta de uma palavra. Quem chama é que faz o commit.

    Se o lema já estiver no vocabulário dessa língua, conta mais uma consulta
    e mantém a frase original da primeira vez. Se não, cria a entrada.
    """
    language = document.language or ""
    # casefold é um "minúsculas" mais completo: trata bem o "ß" alemão, por exemplo.
    lemma_key = explanation.lemma.casefold()
    entry = session.scalar(
        select(VocabularyEntry).where(
            VocabularyEntry.language == language, VocabularyEntry.lemma_key == lemma_key
        )
    )
    if entry is None:
        entry = VocabularyEntry(
            language=language,
            lemma_key=lemma_key,
            word=word,
            explanation=explanation.model_dump(),
            sentence_text=sentence.text,
            document_id=document.id,
            sentence_id=sentence.id,
            lookup_count=1,
        )
        session.add(entry)
    else:
        entry.lookup_count += 1
        entry.updated_at = datetime.now(UTC)
    # flush dá um id à entrada nova sem fechar a transação.
    session.flush()
    return entry


def list_entries(
    session: Session, *, limit: int, before_id: int | None, language: str | None
) -> list[VocabularyEntry]:
    """Entradas do vocabulário, da mais recente para a mais antiga."""
    query = select(VocabularyEntry).order_by(VocabularyEntry.id.desc()).limit(limit)
    if before_id is not None:
        query = query.where(VocabularyEntry.id < before_id)
    if language is not None:
        query = query.where(VocabularyEntry.language == language)
    return list(session.scalars(query))


def delete_entry(session: Session, entry_id: int) -> None:
    entry = session.get(VocabularyEntry, entry_id)
    if entry is None:
        raise ProblemError(
            404,
            "vocabulary_entry_not_found",
            "Palavra não encontrada",
            "Essa palavra não está no vocabulário.",
        )
    session.delete(entry)
    session.commit()
