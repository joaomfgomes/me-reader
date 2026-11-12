"""Testes do GET /api/v1/health."""

import json
import logging
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app


def test_health_is_ok_when_everything_works(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "data_dir": "ok", "migrations": "ok", "speech": "ok"},
    }


def test_health_probe_leaves_no_rows_behind(client: TestClient) -> None:
    client.get("/api/v1/health")

    with client.app.state.engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM app_meta")).scalar_one()
    assert count == 0


def test_database_uses_wal_mode(client: TestClient) -> None:
    with client.app.state.engine.connect() as connection:
        mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    assert mode == "wal"


def test_health_fails_when_migrations_are_pending(settings: Settings) -> None:
    # Aqui não usamos a fixture "app": criamos a aplicação sem correr as
    # migrações, que é o estado de quem se esqueceu do "make migrate".
    settings.data_dir.mkdir(parents=True)
    with TestClient(create_app(settings), base_url="http://localhost") as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "health_check_failed"
    assert body["checks"]["migrations"] == "error"
    assert body["checks"]["data_dir"] == "ok"


@pytest.fixture
def read_only_data_dir(settings: Settings) -> Iterator[None]:
    settings.data_dir.chmod(0o555)
    yield
    # Repor as permissões, senão o pytest não consegue apagar a pasta temporária.
    settings.data_dir.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="o utilizador root ignora permissões de ficheiros")
def test_health_fails_when_data_dir_is_read_only(
    client: TestClient, read_only_data_dir: None
) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["checks"]["data_dir"] == "error"


def test_each_response_has_its_own_request_id(client: TestClient) -> None:
    first = client.get("/api/v1/health").headers["x-request-id"]
    second = client.get("/api/v1/health").headers["x-request-id"]

    assert first and second
    assert first != second


def test_requests_are_logged_as_json_with_request_id(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/api/v1/health")

    for handler in logging.getLogger().handlers:
        handler.flush()
    lines = (settings.log_dir / "app.log").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    request_entry = next(entry for entry in entries if entry["message"] == "request")

    assert request_entry["request_id"] == response.headers["x-request-id"]
    assert request_entry["method"] == "GET"
    assert request_entry["path"] == "/api/v1/health"
    assert request_entry["status"] == 200
