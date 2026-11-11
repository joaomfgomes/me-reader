"""Rotas de documentos: importar, listar, ler, corrigir, apagar e guardar a posição."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import SessionDep, StorageDep
from app.api.schemas import (
    ChapterDetail,
    ChapterSummary,
    DocumentDetail,
    DocumentList,
    DocumentSummary,
    DocumentUpdate,
    PositionUpdate,
    ReadingPositionOut,
)
from app.core.errors import ProblemError
from app.importing import validation
from app.importing.language import SUPPORTED_LANGUAGES
from app.importing.models import Block, Chapter, Document, ReadingPosition, Sentence
from app.importing.service import import_epub

router = APIRouter(prefix="/documents", tags=["documents"])


# --- Funções de apoio -------------------------------------------------------


def _get_document(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise ProblemError(
            404,
            "document_not_found",
            "Documento não encontrado",
            "Não existe documento com esse id.",
        )
    return document


def _reading_position(session: Session, document: Document) -> ReadingPositionOut | None:
    position = document.reading_position
    if position is None:
        return None
    # A posição guarda só a frase. O bloco e o capítulo onde ela está
    # obtêm-se subindo pelas ligações: frase -> bloco -> capítulo.
    block_id, chapter_position = session.execute(
        select(Block.id, Chapter.position)
        .join(Chapter, Block.chapter_id == Chapter.id)
        .join(Sentence, Sentence.block_id == Block.id)
        .where(Sentence.id == position.sentence_id)
    ).one()
    return ReadingPositionOut(
        sentence_id=position.sentence_id,
        block_id=block_id,
        chapter_position=chapter_position,
        updated_at=position.updated_at,
    )


def _document_detail(session: Session, document: Document) -> DocumentDetail:
    return DocumentDetail(
        **DocumentSummary.model_validate(document).model_dump(),
        chapters=[ChapterSummary.model_validate(chapter) for chapter in document.chapters],
        reading_position=_reading_position(session, document),
    )


def _encode_cursor(document_id: int) -> str:
    # O cursor é o id do último documento da página, disfarçado em base64 para
    # o cliente o tratar como um valor opaco e não fazer contas com ele.
    return base64.urlsafe_b64encode(str(document_id).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (binascii.Error, ValueError) as exc:
        raise ProblemError(
            422, "invalid_cursor", "Cursor inválido", "Usa o next_cursor da resposta anterior."
        ) from exc


# --- Rotas ------------------------------------------------------------------


# As rotas são "def" e não "async def": usam a base de dados e o disco, que
# bloqueiam. O FastAPI corre-as numa thread à parte, e o servidor continua
# disponível para outros pedidos enquanto um livro é importado.
@router.post("", response_model=DocumentSummary, status_code=201)
def upload_document(
    file: UploadFile, response: Response, session: SessionDep, storage: StorageDep
) -> Document:
    """Importa um EPUB enviado num formulário multipart, no campo "file"."""
    # Lemos no máximo um byte a mais do que o limite: chega para saber que o
    # ficheiro é grande demais sem o carregar todo para memória.
    data = file.file.read(validation.MAX_FILE_BYTES + 1)
    # Não usamos file.filename nem file.content_type: são escolhidos por quem
    # envia. O tipo é verificado pelo conteúdo, dentro de import_epub.
    result = import_epub(session, storage, data)
    if not result.created:
        # 201 quer dizer "criado". Se o livro já existia, respondemos 200.
        response.status_code = 200
    return result.document


@router.get("", response_model=DocumentList)
def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> DocumentList:
    """Biblioteca, do documento mais recente para o mais antigo."""
    # Paginação por cursor: em vez de "salta N linhas" (OFFSET), pedimos "as
    # linhas a seguir a este id". É rápido em qualquer página e não repete nem
    # salta documentos se a biblioteca mudar entre dois pedidos.
    query = select(Document).order_by(Document.id.desc()).limit(limit + 1)
    if cursor is not None:
        query = query.where(Document.id < _decode_cursor(cursor))
    documents = list(session.scalars(query))

    # Pedimos uma linha a mais do que o limite só para saber se há mais páginas.
    has_more = len(documents) > limit
    documents = documents[:limit]
    return DocumentList(
        items=[DocumentSummary.model_validate(document) for document in documents],
        next_cursor=_encode_cursor(documents[-1].id) if has_more else None,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, session: SessionDep) -> DocumentDetail:
    return _document_detail(session, _get_document(session, document_id))


@router.patch("/{document_id}", response_model=DocumentDetail)
def update_document(
    document_id: int, changes: DocumentUpdate, session: SessionDep
) -> DocumentDetail:
    """Corrige a língua ou a marca "privado". Só altera os campos enviados."""
    document = _get_document(session, document_id)

    if changes.language is not None:
        if changes.language not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ProblemError(
                422,
                "unsupported_language",
                "Língua não suportada",
                f"As línguas suportadas são: {supported}.",
            )
        # Só muda o campo. A divisão em frases feita na importação mantém-se,
        # para as posições guardadas continuarem válidas.
        document.language = changes.language
    if changes.is_private is not None:
        document.is_private = changes.is_private

    session.commit()
    return _document_detail(session, document)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, session: SessionDep, storage: StorageDep) -> None:
    """Apaga o documento, os seus capítulos e o ficheiro original."""
    document = _get_document(session, document_id)
    storage_key = document.storage_key

    session.delete(document)
    session.commit()
    # Primeiro a base de dados, depois o ficheiro. Se a app parar entre os dois
    # passos sobra um ficheiro sem dono, que é inofensivo; a ordem inversa
    # podia deixar um documento listado sem o seu original.
    storage.delete(storage_key)


@router.get("/{document_id}/chapters/{position}", response_model=ChapterDetail)
def get_chapter(document_id: int, position: int, session: SessionDep) -> Chapter:
    """Texto de um capítulo. "position" começa em 0, como em DocumentDetail.chapters."""
    _get_document(session, document_id)
    chapter = session.scalar(
        select(Chapter)
        .where(Chapter.document_id == document_id, Chapter.position == position)
        # selectinload carrega os blocos e as frases em duas consultas extra.
        # Sem ele, o ORM faria uma consulta por bloco ao percorrer as frases
        # (o chamado problema "N+1").
        .options(selectinload(Chapter.blocks).selectinload(Block.sentences))
    )
    if chapter is None:
        raise ProblemError(
            404,
            "chapter_not_found",
            "Capítulo não encontrado",
            "O documento não tem esse capítulo.",
        )
    return chapter


@router.put("/{document_id}/position", response_model=ReadingPositionOut)
def save_position(
    document_id: int, body: PositionUpdate, session: SessionDep
) -> ReadingPositionOut:
    """Guarda a frase onde o leitor parou. Substitui a posição anterior."""
    document = _get_document(session, document_id)

    # Confirma que a frase pertence a este documento, subindo até ao capítulo.
    belongs = session.scalar(
        select(Sentence.id)
        .join(Block, Sentence.block_id == Block.id)
        .join(Chapter, Block.chapter_id == Chapter.id)
        .where(Sentence.id == body.sentence_id, Chapter.document_id == document_id)
    )
    if belongs is None:
        raise ProblemError(
            422,
            "sentence_not_in_document",
            "Frase inválida",
            "Essa frase não pertence a este documento.",
        )

    now = datetime.now(UTC)
    if document.reading_position is None:
        document.reading_position = ReadingPosition(sentence_id=body.sentence_id, updated_at=now)
    else:
        document.reading_position.sentence_id = body.sentence_id
        document.reading_position.updated_at = now
    session.commit()

    position = _reading_position(session, document)
    assert position is not None  # acabámos de a gravar
    return position
