"""Testes da validação do cabeçalho Host (regra fixa 7)."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8000",
        # Tentativas de enganar uma comparação mal feita (por prefixo ou sufixo).
        "localhost.evil.example",
        "evil-localhost",
        "127.0.0.1.evil.example",
        # Morada da rede local: a app não deve responder por ela.
        "192.168.1.10:8000",
        "",
    ],
)
def test_requests_with_foreign_host_are_rejected(client: TestClient, host: str) -> None:
    response = client.get("/api/v1/health", headers={"Host": host})

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "invalid_host"
    # Até os pedidos rejeitados levam identificador, para se acharem nos logs.
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "host", ["localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:5173", "LOCALHOST:8000"]
)
def test_requests_with_local_host_are_accepted(client: TestClient, host: str) -> None:
    response = client.get("/api/v1/health", headers={"Host": host})

    assert response.status_code == 200


def test_no_cors_headers_are_sent(client: TestClient) -> None:
    # Sem Access-Control-Allow-Origin, o browser não deixa uma página de outra
    # origem ler a resposta.
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
