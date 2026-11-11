"""Testes das migrações e da cópia de segurança que as antecede."""

import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command

from app.core.backup import backup_database
from app.core.config import Settings
from app.core.db import get_alembic_config, run_migrations


def backups_of(settings: Settings) -> list[Path]:
    return sorted((settings.data_dir / "backups").glob("*.db"))


def test_models_and_migrations_describe_the_same_schema(settings: Settings) -> None:
    run_migrations(settings.database_url)

    # "alembic check" falha se os modelos tiverem tabelas ou colunas que
    # nenhuma migração cria. Apanha o esquecimento de gerar uma migração.
    command.check(get_alembic_config(settings.database_url))


def test_new_database_is_migrated_without_a_backup(settings: Settings) -> None:
    run_migrations(settings.database_url)

    assert backups_of(settings) == []


def test_existing_database_is_backed_up_before_pending_migrations(settings: Settings) -> None:
    # Deixa a base de dados na primeira revisão, como numa instalação antiga.
    command.upgrade(get_alembic_config(settings.database_url), "0001")

    run_migrations(settings.database_url)

    (backup,) = backups_of(settings)
    # A cópia é uma base de dados válida, no estado anterior à migração.
    with closing(sqlite3.connect(backup)) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert version == ("0001",)
    assert "app_meta" in tables
    assert "documents" not in tables


def test_no_backup_when_there_is_nothing_to_migrate(settings: Settings) -> None:
    run_migrations(settings.database_url)
    run_migrations(settings.database_url)

    assert backups_of(settings) == []


def test_only_the_most_recent_backups_are_kept(settings: Settings) -> None:
    run_migrations(settings.database_url)

    created = [backup_database(settings.database_url, keep=3) for _ in range(5)]

    assert backups_of(settings) == created[-3:]


def test_backup_of_a_missing_database_does_nothing(settings: Settings) -> None:
    assert backup_database(settings.database_url) is None
    assert not (settings.data_dir / "backups").exists()
