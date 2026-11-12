"""Rotas do tutor e do vocabulário."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, SettingsDep, TutorDep
from app.api.pagination import decode_cursor, encode_cursor
from app.api.schemas import (
    VocabularyEntryOut,
    VocabularyList,
    WordExplanationOut,
    WordRequest,
    WordResponse,
)
from app.core.errors import ProblemError
from app.importing.language import SUPPORTED_LANGUAGES
from app.tutor.service import explain_word
from app.vocabulary.service import delete_entry, list_entries

router = APIRouter(tags=["tutor"])


@router.post("/tutor/word", response_model=WordResponse)
def explain_word_route(
    body: WordRequest, session: SessionDep, tutor: TutorDep, settings: SettingsDep
) -> WordResponse:
    """Explica uma palavra no contexto da sua frase e junta-a ao vocabulário.

    É um POST porque pode ter efeitos: gastar dinheiro e enviar texto para
    fora do portátil.
    """
    result = explain_word(
        session,
        tutor,
        settings,
        body.sentence_id,
        body.word_start,
        body.word_end,
        confirm_private=body.confirm_private,
    )
    return WordResponse(
        word=result.word,
        sentence_id=body.sentence_id,
        explanation=WordExplanationOut.model_validate(result.explanation),
        cached=result.cached,
        vocabulary_entry_id=result.vocabulary_entry.id,
    )


@router.get("/vocabulary", response_model=VocabularyList)
def list_vocabulary(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    language: str | None = None,
) -> VocabularyList:
    """Palavras consultadas, da mais recente para a mais antiga."""
    if language is not None and language not in SUPPORTED_LANGUAGES:
        raise ProblemError(
            422, "unsupported_language", "Língua não suportada", "Essa língua não é suportada."
        )
    before_id = decode_cursor(cursor) if cursor is not None else None
    # Uma entrada a mais do que o limite, só para saber se há mais páginas.
    entries = list_entries(session, limit=limit + 1, before_id=before_id, language=language)
    has_more = len(entries) > limit
    entries = entries[:limit]
    return VocabularyList(
        items=[VocabularyEntryOut.model_validate(entry) for entry in entries],
        next_cursor=encode_cursor(entries[-1].id) if has_more else None,
    )


@router.delete("/vocabulary/{entry_id}", status_code=204)
def delete_vocabulary_entry(entry_id: int, session: SessionDep) -> None:
    delete_entry(session, entry_id)
