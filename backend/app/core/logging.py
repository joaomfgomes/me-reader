"""Logs estruturados em JSON, com o identificador do pedido em cada linha.

Regra fixa 9: os logs levam identificadores, tamanhos e durações. Nunca chaves
de API nem texto dos documentos.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Uma ContextVar é uma variável com um valor independente por pedido em curso.
# Com vários pedidos a serem tratados ao mesmo tempo, uma variável global normal
# misturaria os identificadores; esta não. O middleware define o valor no início
# do pedido e o formatador lê-o ao escrever cada linha.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Atributos que qualquer LogRecord tem de origem. Tudo o que não estiver aqui
# foi passado por nós em extra={...} e deve aparecer no JSON.
# "color_message" é uma cópia da mensagem com códigos de cor que o uvicorn
# junta para o terminal; num log em JSON só fazia ruído.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "color_message",
}

# Handlers criados por configure_logging, para os podermos substituir sem mexer
# nos de outras ferramentas (o pytest, por exemplo, também liga os seus).
_installed_handlers: list[logging.Handler] = []


class JsonFormatter(logging.Formatter):
    """Transforma cada registo numa linha de JSON.

    Uma linha por evento, com campos fixos, é fácil de filtrar com ferramentas
    como o jq (por exemplo, todas as linhas de um request_id).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        # default=str evita que um valor não serializável (um Path, uma data)
        # rebente o log; ensure_ascii=False mantém os acentos legíveis.
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str, log_dir: Path | None = None) -> None:
    """Liga os logs ao terminal e, se for dada uma pasta, a um ficheiro com rotação."""
    root = logging.getLogger()
    for handler in _installed_handlers:
        root.removeHandler(handler)
        handler.close()
    _installed_handlers.clear()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            # Rotação: ao chegar a 5 MB o ficheiro passa a app.log.1 e começa
            # um novo. Ficam no máximo 5 antigos, para o disco não encher.
            handlers.append(
                RotatingFileHandler(
                    log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
                )
            )
        except OSError:
            # Sem permissão de escrita na pasta de dados a app arranca na mesma,
            # só com logs no terminal. O /health é que denuncia o problema.
            pass

    formatter = JsonFormatter()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
        _installed_handlers.append(handler)
    root.setLevel(level.upper())
    # O Alembic escreve duas linhas INFO sempre que consultamos a revisão atual,
    # o que acontece em cada /health. Dele só nos interessam avisos e erros.
    logging.getLogger("alembic").setLevel(logging.WARNING)
