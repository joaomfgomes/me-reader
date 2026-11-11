"""Ponto de entrada do Alembic: corre sempre que se executa um comando alembic."""

from alembic import context
from alembic.runtime.migration import MigrationContext

from app.core.backup import backup_database
from app.core.config import Settings
from app.core.db import Base, create_db_engine, ensure_database_dir

# Importar os modelos regista as tabelas em Base.metadata. Sem este import o
# Alembic não as veria. O "noqa" diz ao ruff que o import parece não ser usado,
# mas é intencional.
from app.importing import models  # noqa: F401

config = context.config

# O Alembic compara estas tabelas (as declaradas no código) com a base de dados
# quando lhe pedimos para gerar uma migração com "--autogenerate".
target_metadata = Base.metadata

# Os testes passam o URL de uma base de dados temporária pela configuração.
# Na linha de comandos não vem nenhum, e usamos o da aplicação.
database_url = config.get_main_option("sqlalchemy.url") or Settings().database_url


def run_migrations() -> None:
    ensure_database_dir(database_url)
    # Usamos a mesma função da aplicação para o modo WAL também valer aqui.
    engine = create_db_engine(database_url)

    # Antes de alterar o esquema de uma base de dados que já tem dados,
    # guardamos uma cópia. Se a migração correr mal, recupera-se repondo esse
    # ficheiro. Não há cópia quando a base de dados é nova (revisão None) nem
    # quando já está na última versão (não há nada para alterar).
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision is not None and current_revision != context.get_head_revision():
        backup_database(database_url)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # O SQLite quase não suporta ALTER TABLE. Em "batch mode" o Alembic
            # contorna isso recriando a tabela; noutras bases de dados não muda nada.
            render_as_batch=True,
        )
        # Cada migração corre dentro de uma transação: ou aplica tudo, ou nada.
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
