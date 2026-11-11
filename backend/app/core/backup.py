"""Cópias de segurança da base de dados."""

import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

BACKUPS_TO_KEEP = 7


def backup_database(database_url: str, keep: int = BACKUPS_TO_KEEP) -> Path | None:
    """Copia a base de dados para a pasta "backups" ao lado dela.

    Devolve o caminho da cópia, ou None se não havia nada para copiar.

    Este módulo é específico de SQLite de propósito: fazer cópias de segurança
    depende sempre do motor de base de dados. Numa versão com Postgres seria
    substituído pelas ferramentas dele, sem afetar o resto da aplicação.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    source_path = Path(url.database)
    if not source_path.is_file():
        return None

    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    # A data no nome, do maior para o menor (ano, mês, dia, ...), faz com que a
    # ordem alfabética dos ficheiros seja também a ordem cronológica.
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target_path = backup_dir / f"{source_path.stem}-{timestamp}.db"

    # Copiar o ficheiro com um simples "cp" não é seguro: em modo WAL parte dos
    # dados está num segundo ficheiro, e pode haver uma escrita a decorrer.
    # A API de backup do SQLite produz sempre uma cópia consistente.
    with (
        closing(sqlite3.connect(source_path)) as source,
        closing(sqlite3.connect(target_path)) as target,
    ):
        source.backup(target)

    # Apaga as cópias mais antigas, deixando só as "keep" mais recentes.
    backups = sorted(backup_dir.glob(f"{source_path.stem}-*.db"))
    for old_backup in backups[:-keep]:
        old_backup.unlink()

    logger.info(
        "database_backup_created",
        extra={"backup_file": target_path.name, "size_bytes": target_path.stat().st_size},
    )
    return target_path
