"""Ponto de entrada do Alembic: corre sempre que se executa um comando alembic."""

from alembic import context

from app.core.config import Settings
from app.core.db import Base, create_db_engine, ensure_database_dir

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
