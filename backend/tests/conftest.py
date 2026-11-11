"""Fixtures partilhadas pelos testes.

Uma fixture é uma função que prepara algo de que os testes precisam. Um teste
recebe-a ao declarar um parâmetro com o mesmo nome; o pytest trata do resto.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import run_migrations
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # tmp_path é uma pasta temporária, nova em cada teste. Os testes nunca
    # tocam na pasta data/ verdadeira nem dependem uns dos outros.
    # _env_file=None impede que o .env da máquina influencie os testes.
    return Settings(data_dir=tmp_path / "data", _env_file=None)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Aplicação com a base de dados temporária já migrada."""
    run_migrations(settings.database_url)
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # O TestClient chama a app diretamente, sem abrir portas de rede.
    # Por omissão envia "Host: testserver", que a nossa validação rejeita;
    # com este base_url passa a enviar "Host: localhost".
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client
