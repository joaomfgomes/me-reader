"""Ligação à base de dados, modelos base e acesso às migrações Alembic."""

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Engine, MetaData, String, Text, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import BACKEND_DIR


class UtcDateTime(TypeDecorator):
    """Coluna de data e hora que é sempre UTC e sempre traz o fuso horário.

    O SQLite não guarda fusos horários: uma data gravada com fuso volta sem
    ele ("naive"). O Postgres devolve-a com fuso. Este tipo iguala os dois
    comportamentos, para o código e a API verem sempre datas em UTC com fuso
    explícito, seja qual for a base de dados.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        # A caminho da base de dados: recusar datas sem fuso evita gravar uma
        # hora local a pensar que é UTC.
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: usa datetime.now(UTC)")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        # A caminho do código: se veio sem fuso (SQLite), sabemos que é UTC.
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    """Classe-mãe de todos os modelos.

    O SQLAlchemy regista em Base.metadata todas as tabelas declaradas por
    subclasses. O Alembic usa esse registo para comparar o código com a base
    de dados quando gera uma migração.
    """

    # Regra para dar nome a chaves e restrições (por exemplo
    # "uq_chapters_document_id"). Sem nomes explícitos cada base de dados
    # inventa os seus, e uma migração futura que precise de alterar uma
    # restrição não saberia como a referir.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class AppMeta(Base):
    """Pares chave/valor sobre a própria instalação.

    Na Fase 0 serve sobretudo para o /health ter uma tabela onde testar a
    escrita. As entidades do domínio (documentos, capítulos, ...) entram na Fase 1.
    """

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


def create_db_engine(database_url: str) -> Engine:
    """Cria o "engine", o objeto que gere as ligações à base de dados.

    Criar o engine não abre nenhuma ligação; isso só acontece no primeiro uso.
    """
    engine = create_engine(database_url)

    # Tudo o que é específico de SQLite fica aqui, atrás deste "if". O resto da
    # app usa SQL portável, para a migração para Postgres ser possível (ADR-002).
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):
            # Este código corre sempre que é aberta uma ligação nova.
            cursor = dbapi_connection.cursor()
            # WAL (write-ahead log): as escritas vão para um ficheiro à parte,
            # e por isso quem lê não bloqueia quem escreve, nem o contrário.
            cursor.execute("PRAGMA journal_mode=WAL")
            # O SQLite só verifica chaves estrangeiras se lho pedirmos, e o
            # pedido vale por ligação. O Postgres verifica sempre.
            cursor.execute("PRAGMA foreign_keys=ON")
            # Se outra ligação estiver a escrever, espera até 5 s em vez de
            # falhar de imediato com "database is locked".
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Cria a fábrica de sessões.

    Uma sessão é uma unidade de trabalho do ORM: junta as alterações feitas a
    objetos Python e envia-as para a base de dados numa transação, no commit.
    Abre-se uma por operação ("with session_factory() as session:").
    """
    # expire_on_commit=False deixa os objetos utilizáveis depois do commit sem
    # obrigar a nova leitura da base de dados.
    return sessionmaker(engine, expire_on_commit=False)


def ensure_database_dir(database_url: str) -> None:
    """Cria a pasta do ficheiro SQLite, se ainda não existir."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def get_alembic_config(database_url: str) -> Config:
    """Configuração do Alembic a apontar para uma base de dados concreta.

    Passar o URL por aqui permite que os testes corram as migrações numa base
    de dados temporária, sem tocar na verdadeira.
    """
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_migrations(database_url: str) -> None:
    """Aplica todas as migrações em falta (equivale a "alembic upgrade head")."""
    command.upgrade(get_alembic_config(database_url), "head")


def get_migration_status(engine: Engine) -> tuple[str | None, str | None]:
    """Devolve (revisão aplicada na base de dados, última revisão no código).

    O Alembic guarda a revisão aplicada na tabela alembic_version. Se as duas
    forem iguais, não há migrações por correr.
    """
    script = ScriptDirectory.from_config(get_alembic_config(str(engine.url)))
    head = script.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current, head
