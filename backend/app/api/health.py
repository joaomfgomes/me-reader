"""GET /api/v1/health: diz se o sistema está em condições de funcionar."""

import logging
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import Engine, insert

from app.core.db import AppMeta, get_migration_status
from app.core.errors import ProblemError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

CheckStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Corpo da resposta quando está tudo bem.

    Declarar a resposta como modelo Pydantic faz o FastAPI validá-la e
    documentá-la automaticamente em /docs.
    """

    # "degraded": o essencial funciona, mas um serviço externo está a falhar.
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]


# Depois deste tempo sem novas falhas, deixamos de assinalar o serviço de voz.
SPEECH_FAILURE_WINDOW = timedelta(minutes=10)


def speech_status(speech: object) -> CheckStatus:
    """Estado do serviço de voz, pelo resultado da última síntese pedida.

    Não fazemos uma chamada de teste ao fornecedor: custaria quota a cada
    verificação. Olhamos para o que aconteceu da última vez que foi usado.
    """
    last_failure = getattr(speech, "last_failure_at", None)
    recent = last_failure is not None and datetime.now(UTC) - last_failure < SPEECH_FAILURE_WINDOW
    return "error" if recent else "ok"


def check_database_writable(engine: Engine) -> None:
    """Prova que a base de dados aceita escrita, sem deixar lixo.

    Insere uma linha e desfaz a transação. O INSERT obriga o SQLite a obter o
    bloqueio de escrita e a escrever no ficheiro; o rollback garante que a
    linha nunca chega a existir.
    """
    with engine.connect() as connection:
        connection.execute(
            insert(AppMeta).values(key="health_probe", value="ok", updated_at=datetime.now(UTC))
        )
        connection.rollback()


def check_data_dir_writable(data_dir: Path) -> None:
    """Prova que conseguimos criar ficheiros na pasta de dados."""
    # O ficheiro temporário é apagado automaticamente ao sair do "with".
    with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".health-") as probe:
        probe.write(b"ok")
        probe.flush()


def check_migrations_current(engine: Engine) -> None:
    """Prova que a base de dados está na última versão do esquema."""
    current, head = get_migration_status(engine)
    if current != head:
        raise RuntimeError("pending migrations")


def _run(name: str, check: Callable[[], None]) -> CheckStatus:
    try:
        check()
    except Exception as exc:
        # Regista o tipo de erro para diagnóstico, sem a mensagem completa.
        logger.warning(
            "health_check_failed", extra={"check": name, "error_type": type(exc).__name__}
        )
        return "error"
    return "ok"


# A função é "def" e não "async def" de propósito: as verificações bloqueiam
# (disco e base de dados). O FastAPI corre funções "def" numa thread à parte,
# e assim o servidor continua livre para outros pedidos.
@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    engine: Engine = request.app.state.engine
    data_dir: Path = request.app.state.settings.data_dir

    checks: dict[str, CheckStatus] = {
        "database": _run("database", lambda: check_database_writable(engine)),
        "data_dir": _run("data_dir", lambda: check_data_dir_writable(data_dir)),
        "migrations": _run("migrations", lambda: check_migrations_current(engine)),
    }

    if any(status == "error" for status in checks.values()):
        # 503 (serviço indisponível) e não 200: quem monitoriza percebe pelo
        # código de estado, sem ter de ler o corpo.
        raise ProblemError(
            503,
            "health_check_failed",
            "Sistema com problemas",
            "Pelo menos uma verificação falhou. Corre 'make migrate' e confirma "
            "as permissões da pasta de dados.",
            checks=checks,
        )
    # O serviço de voz é externo: se falhar, a leitura e o áudio em cache
    # continuam a funcionar. Por isso não entra nas verificações acima, que
    # dão 503; só muda o estado para "degradado", com resposta 200.
    checks["speech"] = speech_status(request.app.state.speech)
    status = "degraded" if checks["speech"] == "error" else "ok"
    return HealthResponse(status=status, checks=checks)
