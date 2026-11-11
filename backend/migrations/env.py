"""Ponto de entrada do Alembic: corre sempre que se executa um comando alembic."""

from alembic import context
from alembic.runtime.migration import MigrationContext

# Importar os modelos regista as tabelas em Base.metadata. Sem este import o
# Alembic não as veria. O "noqa" diz ao ruff que o import parece não ser usado,
# mas é intencional.
import app.audio.models  # noqa: F401
import app.importing.models  # noqa: F401
import app.usage.models  # noqa: F401
from app.core.backup import backup_database
from app.core.config import Settings
from app.core.db import Base, UtcDateTime, create_db_engine, ensure_database_dir

config = context.config

# O Alembic compara estas tabelas (as declaradas no código) com a base de dados
# quando lhe pedimos para gerar uma migração com "--autogenerate".
target_metadata = Base.metadata

# Os testes passam o URL de uma base de dados temporária pela configuração.
# Na linha de comandos não vem nenhum, e usamos o da aplicação.
database_url = config.get_main_option("sqlalchemy.url") or Settings().database_url


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Diz ao Alembic como escrever certos tipos nas migrações que gera.

    Sem isto, uma coluna UtcDateTime apareceria como "app.core.db.UtcDateTime()",
    e a migração passaria a depender do código da aplicação. Uma migração deve
    usar só tipos do SQLAlchemy, para continuar a funcionar se o código mudar.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    # False: usar a forma normal para tudo o resto.
    return False


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
            render_item=render_item,
            # O SQLite quase não suporta ALTER TABLE. Em "batch mode" o Alembic
            # contorna isso recriando a tabela; noutras bases de dados não muda nada.
            render_as_batch=True,
        )
        # Cada migração corre dentro de uma transação: ou aplica tudo, ou nada.
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
