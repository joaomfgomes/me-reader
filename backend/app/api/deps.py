"""Dependências partilhadas pelas rotas.

No FastAPI, uma "dependência" é uma função cujo resultado é entregue à rota
que o pede com Depends(...). Serve para as rotas receberem o que precisam
(uma sessão de base de dados, o armazenamento) sem saberem como se obtém.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.storage.base import FileStorage


def get_session(request: Request) -> Iterator[Session]:
    # Uma sessão por pedido. O "yield" entrega-a à rota; quando a rota termina,
    # o "with" fecha a sessão, mesmo que tenha havido um erro.
    with request.app.state.session_factory() as session:
        yield session


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


# Atalhos para escrever "session: SessionDep" nos parâmetros das rotas.
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]
