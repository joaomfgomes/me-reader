"""Dependências partilhadas pelas rotas.

No FastAPI, uma "dependência" é uma função cujo resultado é entregue à rota
que o pede com Depends(...). Serve para as rotas receberem o que precisam
(uma sessão de base de dados, o armazenamento) sem saberem como se obtém.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.audio.voice import SpeechSynthesizer
from app.core.config import Settings
from app.storage.base import FileStorage


def get_session(request: Request) -> Iterator[Session]:
    # Uma sessão por pedido. O "yield" entrega-a à rota; quando a rota termina,
    # o "with" fecha a sessão, mesmo que tenha havido um erro.
    with request.app.state.session_factory() as session:
        yield session


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


def get_speech(request: Request) -> SpeechSynthesizer:
    return request.app.state.speech


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


# Atalhos para escrever "session: SessionDep" nos parâmetros das rotas.
SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]
SpeechDep = Annotated[SpeechSynthesizer, Depends(get_speech)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
