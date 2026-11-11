"""Testes do formato de erro application/problem+json (regra fixa 11)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROBLEM_FIELDS = {"type", "title", "status", "code"}


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert PROBLEM_FIELDS <= body.keys()
    assert body["status"] == 404
    assert body["code"] == "not_found"


def test_wrong_method_returns_problem_json(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "method_not_allowed"


def test_validation_error_does_not_echo_the_input(app: FastAPI, client: TestClient) -> None:
    # Rota criada só para o teste, com um parâmetro que tem de ser um inteiro.
    @app.get("/api/v1/_test/items/{item_id}")
    def _get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    response = client.get("/api/v1/_test/items/texto-secreto")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"
    assert "texto-secreto" not in response.text


def test_unexpected_error_returns_problem_json_without_details(
    app: FastAPI, client: TestClient
) -> None:
    @app.get("/api/v1/_test/boom")
    def _boom() -> None:
        raise RuntimeError("texto-secreto")

    response = client.get("/api/v1/_test/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "internal_error"
    # A mensagem da exceção não pode chegar ao cliente.
    assert "texto-secreto" not in response.text
    assert response.headers["x-request-id"] in response.json()["detail"]
