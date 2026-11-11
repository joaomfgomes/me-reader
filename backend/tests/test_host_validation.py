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


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://localhost.evil.example",
        "http://192.168.1.10:5173",
        # Páginas abertas de um ficheiro ou de uma iframe isolada enviam "null".
        "null",
    ],
)
def test_writes_from_other_sites_are_rejected(client: TestClient, origin: str) -> None:
    # Um formulário multipart é dos poucos pedidos de escrita que o browser
    # deixa outro site enviar sem pedir autorização primeiro.
    response = client.post(
        "/api/v1/documents", files={"file": ("b.epub", b"x")}, headers={"Origin": origin}
    )

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "cross_site_request"


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173", None])
def test_writes_from_the_app_itself_or_without_origin_are_accepted(
    client: TestClient, origin: str | None
) -> None:
    headers = {"Origin": origin} if origin else {}

    response = client.post("/api/v1/documents", files={"file": ("b.epub", b"x")}, headers=headers)

    # Passa a verificação de origem e chega à rota, que recusa o ficheiro por
    # não ser um EPUB.
    assert response.status_code == 415


def test_reads_are_not_affected_by_the_origin_check(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
