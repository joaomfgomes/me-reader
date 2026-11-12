"""Explicação de uma palavra: devolver a que está em cache ou pedi-la ao tutor."""

import hashlib
import html
import json
import logging
import threading
import time
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ProblemError
from app.importing.models import Block, Chapter, Document, Sentence
from app.tutor.models import TutorResponse
from app.tutor.prompts import WORD_PROMPT_VERSION, load_prompt
from app.tutor.tutor import Tutor, TutorProviderError, WordExplanation
from app.usage.service import llm_cost_this_month, record_llm_usage
from app.vocabulary.models import VocabularyEntry
from app.vocabulary.service import record_lookup

logger = logging.getLogger(__name__)

WORD = "word"

# Quantas vezes pedimos a resposta ao modelo antes de desistir: a primeira e
# uma nova tentativa se ela vier num formato inválido.
MAX_ATTEMPTS = 2

LANGUAGE_NAMES = {
    "en": "inglês",
    "es": "espanhol",
    "fr": "francês",
    "de": "alemão",
    "it": "italiano",
}

# Um cadeado por chave de cache, como no áudio: dois pedidos simultâneos da
# mesma palavra pagam uma só chamada ao modelo.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def tutor_cache_key(
    sentence: str, word: str, kind: str, model: str, prompt_version: int, language: str
) -> str:
    """Chave de cache de uma resposta do tutor (ADR-004).

    Junta tudo o que muda a resposta: a frase, a palavra, o tipo de pedido, o
    modelo e a versão do prompt. A língua também entra, porque a mesma grafia
    pode existir em duas línguas com sentidos diferentes. As frases vizinhas,
    que vão como contexto, ficam de fora: ajudam o modelo, mas a mesma frase
    noutro sítio deve reaproveitar a explicação.
    """
    payload = json.dumps(
        [sentence, word, kind, model, prompt_version, language], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_word_message(
    word: str, sentence: str, before: str | None, after: str | None, language: str
) -> str:
    """Monta a mensagem com o texto do livro, sempre dentro de etiquetas.

    As etiquetas separam o que é material do livro do que são instruções
    nossas (que vão no prompt de sistema). É a defesa contra texto do livro que
    tente dar ordens ao modelo, a chamada "injeção de prompt".

    Para a separação valer, o texto do livro não pode conter etiquetas: uma
    frase com "</frase>" lá dentro fecharia a etiqueta e o resto passaria por
    instruções. Por isso os sinais "<" e ">" do livro são convertidos em
    "&lt;" e "&gt;", que o modelo lê como os mesmos sinais, mas que não abrem
    nem fecham nada.
    """

    def data(text: str) -> str:
        return html.escape(text, quote=False)

    context = " ".join(part for part in (before, sentence, after) if part)
    return (
        f"Língua do texto: {LANGUAGE_NAMES.get(language, language)}\n\n"
        f"<contexto>\n{data(context)}\n</contexto>\n\n"
        f"<frase>\n{data(sentence)}\n</frase>\n\n"
        f"<palavra>{data(word)}</palavra>"
    )


@dataclass(frozen=True)
class WordResult:
    word: str
    explanation: WordExplanation
    # True se a explicação já existia e nada foi pedido ao modelo.
    cached: bool
    vocabulary_entry: VocabularyEntry


def _load_sentence(session: Session, sentence_id: int) -> tuple[Sentence, Block, Document]:
    row = session.execute(
        select(Sentence, Block, Document)
        .join(Block, Sentence.block_id == Block.id)
        .join(Chapter, Block.chapter_id == Chapter.id)
        .join(Document, Chapter.document_id == Document.id)
        .where(Sentence.id == sentence_id)
    ).one_or_none()
    if row is None:
        raise ProblemError(
            404, "sentence_not_found", "Frase não encontrada", "Essa frase não existe."
        )
    return row.Sentence, row.Block, row.Document


def explain_word(
    session: Session,
    tutor: Tutor,
    settings: Settings,
    sentence_id: int,
    word_start: int,
    word_end: int,
    *,
    confirm_private: bool = False,
) -> WordResult:
    """Explica a palavra em [word_start, word_end) do bloco da frase dada."""
    sentence, block, document = _load_sentence(session, sentence_id)

    # A palavra tem de ser uma das que a importação identificou nesta frase.
    # Assim só sai para o modelo texto que está mesmo no documento, e nunca
    # um pedaço arbitrário escolhido por quem faz o pedido.
    if [word_start, word_end] not in sentence.words:
        raise ProblemError(
            422, "word_not_in_sentence", "Palavra inválida", "Essa palavra não pertence à frase."
        )
    word = block.text[word_start:word_end]

    if document.language is None:
        raise ProblemError(
            422,
            "language_required",
            "Falta a língua do documento",
            "Escolhe a língua do documento na biblioteca antes de pedir explicações.",
        )

    key = tutor_cache_key(
        sentence.text, word, WORD, tutor.model, WORD_PROMPT_VERSION, document.language
    )
    with _lock_for(key):
        stored = session.scalar(select(TutorResponse).where(TutorResponse.content_hash == key))
        cached = stored is not None
        if stored is None:
            stored = _ask_tutor(
                session, tutor, settings, sentence, block, document, word, key, confirm_private
            )
        else:
            record_llm_usage(
                session,
                settings,
                provider=stored.provider,
                document_id=document.id,
                characters=len(sentence.text),
                cache_hit=True,
            )

        explanation = WordExplanation.model_validate(stored.response)
        entry = record_lookup(session, document, sentence, word, explanation)
        session.commit()

    return WordResult(word=word, explanation=explanation, cached=cached, vocabulary_entry=entry)


def _neighbours(session: Session, sentence: Sentence) -> tuple[str | None, str | None]:
    """Texto das frases imediatamente antes e depois, dentro do mesmo bloco."""
    texts = dict(
        session.execute(
            select(Sentence.position, Sentence.text).where(
                Sentence.block_id == sentence.block_id,
                Sentence.position.in_([sentence.position - 1, sentence.position + 1]),
            )
        ).all()
    )
    return texts.get(sentence.position - 1), texts.get(sentence.position + 1)


def _ask_tutor(
    session: Session,
    tutor: Tutor,
    settings: Settings,
    sentence: Sentence,
    block: Block,
    document: Document,
    word: str,
    key: str,
    confirm_private: bool,
) -> TutorResponse:
    before, after = _neighbours(session, sentence)
    user_message = build_word_message(word, sentence.text, before, after, document.language or "")

    # Só chegamos aqui quando o texto vai mesmo sair do portátil. Explicações
    # em cache aparecem sem confirmação, porque nada é enviado.
    if document.is_private and not confirm_private:
        raise ProblemError(
            409,
            "private_document_confirmation_required",
            "Documento privado",
            "Este documento está marcado como privado. Para explicar a palavra, a frase e as "
            "duas frases vizinhas são enviadas ao serviço do tutor; confirma para continuar.",
            characters=len(user_message),
        )

    spent = llm_cost_this_month(session)
    if spent >= settings.monthly_llm_usd_limit:
        raise ProblemError(
            429,
            "llm_budget_exceeded",
            "Teto mensal do tutor atingido",
            "As explicações já pedidas continuam disponíveis. O teto volta a zero no início "
            "do próximo mês, ou podes aumentá-lo no ficheiro .env.",
            monthly_usd_limit=settings.monthly_llm_usd_limit,
            estimated_cost_usd=round(spent, 6),
        )

    system_prompt = load_prompt(WORD, WORD_PROMPT_VERSION)
    explanation: WordExplanation | None = None
    started_at = time.perf_counter()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = tutor.explain_word(system_prompt, user_message, WordExplanation)
        except TutorProviderError as exc:
            # O que já foi gasto em tentativas anteriores fica registado.
            session.commit()
            logger.warning("tutor_provider_error", extra={"provider": tutor.name})
            raise ProblemError(
                502,
                "tutor_provider_error",
                "O serviço do tutor falhou",
                "Não foi possível obter a explicação. Tenta outra vez daqui a pouco.",
            ) from exc

        # Cada chamada custa dinheiro, mesmo que a resposta venha inválida,
        # por isso todas ficam registadas no consumo.
        record_llm_usage(
            session,
            settings,
            provider=tutor.name,
            document_id=document.id,
            characters=len(user_message),
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cache_hit=False,
        )
        try:
            # Valida o JSON e os campos de uma vez. Uma resposta que não
            # cumpra o esquema é tratada como se não tivesse chegado.
            explanation = WordExplanation.model_validate_json(reply.text)
            break
        except ValidationError:
            logger.warning(
                "tutor_invalid_response",
                extra={"provider": tutor.name, "model": tutor.model, "attempt": attempt},
            )

    if explanation is None:
        # Guarda o registo do que foi gasto, mas nenhuma resposta: uma
        # explicação inválida nunca entra na cache (ADR-005).
        session.commit()
        raise ProblemError(
            502,
            "tutor_invalid_response",
            "O tutor respondeu num formato inválido",
            "Não foi possível obter uma explicação utilizável. Tenta outra vez.",
        )

    stored = TutorResponse(
        content_hash=key,
        kind=WORD,
        provider=tutor.name,
        model=tutor.model,
        prompt_version=WORD_PROMPT_VERSION,
        response=explanation.model_dump(),
    )
    try:
        # begin_nested abre um "savepoint": um ponto de retorno dentro da
        # transação. Se este INSERT falhar, só ele é desfeito. Um rollback da
        # transação inteira apagaria também os eventos de consumo registados
        # acima, e o gasto já feito deixaria de contar para o teto mensal.
        with session.begin_nested():
            session.add(stored)
    except IntegrityError:
        # Outro processo gravou a mesma resposta entretanto; usamos a dele.
        return session.scalars(select(TutorResponse).where(TutorResponse.content_hash == key)).one()

    # Só identificadores, contagens e tempos; nunca a frase nem a palavra.
    logger.info(
        "tutor_word_explained",
        extra={
            "document_id": document.id,
            "sentence_id": sentence.id,
            "provider": tutor.name,
            "model": tutor.model,
            "prompt_version": WORD_PROMPT_VERSION,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
        },
    )
    return stored
