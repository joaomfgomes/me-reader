"""Montagem da aplicação FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings
from app.core.db import create_db_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    CrossSiteRequestMiddleware,
    HostValidationMiddleware,
    RequestContextMiddleware,
)
from app.importing import validation
from app.providers import create_speech_synthesizer
from app.storage.disk import DiskStorage

MULTIPART_OVERHEAD_BYTES = 64 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria e configura a aplicação.

    É uma função ("fábrica") em vez de uma variável global "app" para os testes
    poderem criar uma aplicação própria, com uma pasta de dados temporária.
    Importar este módulo não tem efeitos; só chamar create_app() é que tem.
    """
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_dir)
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # O que está antes do "yield" corre no arranque; o que está depois
        # corre ao desligar. Aqui só fechamos as ligações à base de dados.
        yield
        engine.dispose()

    app = FastAPI(title="Leitor de línguas", version="0.1.0", lifespan=lifespan)

    # app.state é o sítio onde se guardam objetos partilhados por toda a app.
    # As rotas chegam a eles através de request.app.state.
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.storage = DiskStorage(settings.data_dir / "files")
    app.state.speech = create_speech_synthesizer(settings)

    register_error_handlers(app)

    # O último middleware adicionado é o que fica mais por fora. Queremos o
    # RequestContext por fora, para que até os pedidos rejeitados pela
    # validação do Host fiquem nos logs e levem identificador.
    # Não há CORSMiddleware de propósito: sem ele, o browser não deixa páginas
    # de outras origens lerem respostas desta API.
    # O limite do corpo é o do ficheiro mais uma folga para o invólucro
    # multipart (delimitadores e cabeçalhos de cada parte).
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=lambda: validation.MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(CrossSiteRequestMiddleware)
    app.add_middleware(HostValidationMiddleware)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router)
    return app
