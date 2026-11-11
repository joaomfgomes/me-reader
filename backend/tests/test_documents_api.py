"""Testes das rotas /api/v1/documents."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.importing import validation
from tests.epub_factory import make_epub

PROBLEM_JSON = "application/problem+json"


def upload(client: TestClient, data: bytes, filename: str = "book.epub"):
    # "files" faz o cliente de teste enviar um formulário multipart, como o
    # browser faz com um <input type="file">.
    return client.post("/api/v1/documents", files={"file": (filename, data)})


def upload_ok(client: TestClient, data: bytes) -> dict:
    response = upload(client, data)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def alice(client: TestClient, alice_bytes: bytes) -> dict:
    """O livro real já importado; devolve o corpo da resposta."""
    return upload_ok(client, alice_bytes)


# --- POST /documents --------------------------------------------------------


def test_upload_imports_the_book(client: TestClient, alice_bytes: bytes) -> None:
    response = upload(client, alice_bytes)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Alice's Adventures in Wonderland"
    assert body["author"] == "Lewis Carroll"
    assert body["language"] == "en"
    assert body["format"] == "epub"
    assert body["is_private"] is False
    assert body["file_size"] == len(alice_bytes)
    assert body["status"] == "ready"
    # As datas saem sempre em UTC com o fuso explícito ("Z" no fim).
    assert body["created_at"].endswith("Z")
    # Detalhes internos não fazem parte do contrato da API.
    assert "file_hash" not in body
    assert "storage_key" not in body


def test_uploading_the_same_file_again_returns_the_existing_document(
    client: TestClient, alice_bytes: bytes, alice: dict
) -> None:
    response = upload(client, alice_bytes, filename="outro-nome.epub")

    assert response.status_code == 200
    assert response.json()["id"] == alice["id"]
    assert len(client.get("/api/v1/documents").json()["items"]) == 1


def test_the_type_is_checked_by_content_not_by_file_name(client: TestClient) -> None:
    response = upload(client, b"isto nao e um epub", filename="livro.epub")

    assert response.status_code == 415
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "unsupported_file_type"


def test_malicious_archive_is_rejected(client: TestClient) -> None:
    response = upload(client, make_epub(overrides={"../../evil.txt": "x"}))

    assert response.status_code == 422
    assert response.json()["code"] == "unsafe_archive"
    assert client.get("/api/v1/documents").json()["items"] == []


def test_upload_without_a_file_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/documents")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_file_over_the_limit_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = make_epub()
    # Limite logo abaixo do tamanho do ficheiro: o pedido cabe na folga do
    # middleware e é a rota que recusa o ficheiro.
    monkeypatch.setattr(validation, "MAX_FILE_BYTES", len(data) - 1)

    response = upload(client, data)

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "file_too_large"


def multipart_body(data: bytes) -> tuple[bytes, str]:
    """Constrói à mão o corpo de um formulário multipart com um ficheiro."""
    boundary = "test-boundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="b.epub"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return (
        head + data + f"\r\n--{boundary}--\r\n".encode(),
        f"multipart/form-data; boundary={boundary}",
    )


def test_oversized_request_is_refused_from_its_declared_size(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validation, "MAX_FILE_BYTES", 1000)
    body, content_type = multipart_body(b"x" * 200_000)

    response = client.post(
        "/api/v1/documents", content=body, headers={"Content-Type": content_type}
    )

    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


def test_oversized_request_without_declared_size_is_cut_while_streaming(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validation, "MAX_FILE_BYTES", 1000)
    body, content_type = multipart_body(b"x" * 200_000)

    def chunks() -> Iterator[bytes]:
        # Enviar um gerador faz o cliente usar "Transfer-Encoding: chunked",
        # sem Content-Length: o servidor não sabe o tamanho à partida.
        for start in range(0, len(body), 10_000):
            yield body[start : start + 10_000]

    response = client.post(
        "/api/v1/documents", content=chunks(), headers={"Content-Type": content_type}
    )

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "file_too_large"


# --- GET /documents ---------------------------------------------------------


def test_empty_library(client: TestClient) -> None:
    assert client.get("/api/v1/documents").json() == {"items": [], "next_cursor": None}


def test_library_is_paginated_newest_first(client: TestClient) -> None:
    ids = [upload_ok(client, make_epub(title=f"Livro {n}"))["id"] for n in range(5)]

    first = client.get("/api/v1/documents", params={"limit": 2}).json()
    second = client.get(
        "/api/v1/documents", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    third = client.get(
        "/api/v1/documents", params={"limit": 2, "cursor": second["next_cursor"]}
    ).json()

    pages = [[item["id"] for item in page["items"]] for page in (first, second, third)]
    assert pages == [[ids[4], ids[3]], [ids[2], ids[1]], [ids[0]]]
    assert first["next_cursor"] and second["next_cursor"]
    assert third["next_cursor"] is None


def test_page_exactly_the_size_of_the_library_has_no_next_cursor(client: TestClient) -> None:
    for n in range(2):
        upload_ok(client, make_epub(title=f"Livro {n}"))

    assert client.get("/api/v1/documents", params={"limit": 2}).json()["next_cursor"] is None


@pytest.mark.parametrize("limit", [0, 101, "abc"])
def test_invalid_limit_is_rejected(client: TestClient, limit: object) -> None:
    response = client.get("/api/v1/documents", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_invalid_cursor_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/documents", params={"cursor": "isto-nao-e-um-cursor"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_cursor"


# --- GET /documents/{id} ----------------------------------------------------


def test_document_detail_lists_the_chapters(client: TestClient, alice: dict) -> None:
    body = client.get(f"/api/v1/documents/{alice['id']}").json()

    assert body["title"] == "Alice's Adventures in Wonderland"
    assert len(body["chapters"]) == 13
    assert body["chapters"][1] == {"position": 1, "title": "CHAPTER I. Down the Rabbit-Hole"}
    assert body["reading_position"] is None


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/documents/999"),
        ("PATCH", "/api/v1/documents/999"),
        ("DELETE", "/api/v1/documents/999"),
        ("GET", "/api/v1/documents/999/chapters/0"),
        ("PUT", "/api/v1/documents/999/position"),
    ],
)
def test_unknown_document_is_404(client: TestClient, method: str, path: str) -> None:
    body = {"sentence_id": 1} if method == "PUT" else {} if method == "PATCH" else None

    response = client.request(method, path, json=body)

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "document_not_found"


def test_document_id_must_be_a_number(client: TestClient) -> None:
    response = client.get("/api/v1/documents/abc")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# --- PATCH /documents/{id} --------------------------------------------------


def test_language_and_private_flag_can_be_corrected(client: TestClient, alice: dict) -> None:
    url = f"/api/v1/documents/{alice['id']}"

    response = client.patch(url, json={"language": "fr", "is_private": True})

    assert response.status_code == 200
    assert response.json()["language"] == "fr"
    assert response.json()["is_private"] is True
    assert client.get(url).json()["language"] == "fr"


def test_patch_only_changes_the_fields_sent(client: TestClient, alice: dict) -> None:
    url = f"/api/v1/documents/{alice['id']}"

    client.patch(url, json={"is_private": True})
    body = client.patch(url, json={}).json()

    assert body["is_private"] is True
    assert body["language"] == "en"
    assert body["title"] == alice["title"]


def test_unsupported_language_is_rejected(client: TestClient, alice: dict) -> None:
    response = client.patch(f"/api/v1/documents/{alice['id']}", json={"language": "pt"})

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_language"


@pytest.mark.parametrize(
    "payload", [{"title": "Outro"}, {"private": True}, {"is_private": "talvez"}]
)
def test_patch_rejects_unknown_fields_and_wrong_types(
    client: TestClient, alice: dict, payload: dict
) -> None:
    response = client.patch(f"/api/v1/documents/{alice['id']}", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# --- DELETE /documents/{id} -------------------------------------------------


def test_delete_removes_the_document_and_its_original_file(
    client: TestClient, alice: dict, settings: Settings
) -> None:
    originals = settings.data_dir / "files" / "originals"
    assert len(list(originals.iterdir())) == 1

    response = client.delete(f"/api/v1/documents/{alice['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/v1/documents/{alice['id']}").status_code == 404
    assert client.get("/api/v1/documents").json()["items"] == []
    assert list(originals.iterdir()) == []


def test_deleted_book_can_be_imported_again(
    client: TestClient, alice: dict, alice_bytes: bytes
) -> None:
    client.delete(f"/api/v1/documents/{alice['id']}")

    assert upload(client, alice_bytes).status_code == 201


# --- GET /documents/{id}/chapters/{position} --------------------------------


def test_chapter_returns_blocks_sentences_and_word_positions(
    client: TestClient, alice: dict
) -> None:
    response = client.get(f"/api/v1/documents/{alice['id']}/chapters/1")

    assert response.status_code == 200
    chapter = response.json()
    assert chapter["document_id"] == alice["id"]
    assert chapter["position"] == 1
    assert chapter["title"] == "CHAPTER I. Down the Rabbit-Hole"
    assert [block["position"] for block in chapter["blocks"]] == list(range(len(chapter["blocks"])))

    # Com o que vem na resposta, o frontend consegue recortar cada frase e
    # cada palavra do texto do bloco.
    block = chapter["blocks"][0]
    first, second = block["sentences"][0], block["sentences"][1]
    assert first["text"] == "CHAPTER I. Down the Rabbit-Hole"
    assert block["text"][second["start_offset"] : second["end_offset"]] == second["text"]
    assert second["text"].startswith("Alice was beginning to get very tired")
    words = [block["text"][start:end] for start, end in second["words"]]
    assert words[:5] == ["Alice", "was", "beginning", "to", "get"]


@pytest.mark.parametrize("position", [13, 99, -1])
def test_unknown_chapter_is_404(client: TestClient, alice: dict, position: int) -> None:
    response = client.get(f"/api/v1/documents/{alice['id']}/chapters/{position}")

    assert response.status_code == 404
    assert response.json()["code"] == "chapter_not_found"


# --- PUT /documents/{id}/position -------------------------------------------


def sentence_id_in(client: TestClient, document_id: int, chapter: int, index: int = 0) -> int:
    body = client.get(f"/api/v1/documents/{document_id}/chapters/{chapter}").json()
    return body["blocks"][0]["sentences"][index]["id"]


def test_reading_position_is_saved_and_shown_in_the_document(
    client: TestClient, alice: dict
) -> None:
    url = f"/api/v1/documents/{alice['id']}"
    sentence_id = sentence_id_in(client, alice["id"], chapter=3, index=2)

    response = client.put(f"{url}/position", json={"sentence_id": sentence_id})

    assert response.status_code == 200
    saved = response.json()
    assert saved["sentence_id"] == sentence_id
    assert saved["chapter_position"] == 3
    assert client.get(url).json()["reading_position"] == saved


def test_saving_again_replaces_the_previous_position(client: TestClient, alice: dict) -> None:
    url = f"/api/v1/documents/{alice['id']}"
    first = sentence_id_in(client, alice["id"], chapter=1)
    second = sentence_id_in(client, alice["id"], chapter=5)

    client.put(f"{url}/position", json={"sentence_id": first})
    client.put(f"{url}/position", json={"sentence_id": second})

    position = client.get(url).json()["reading_position"]
    assert position["sentence_id"] == second
    assert position["chapter_position"] == 5


def test_sentence_from_another_document_is_rejected(client: TestClient, alice: dict) -> None:
    other = upload_ok(client, make_epub())
    foreign_sentence = sentence_id_in(client, other["id"], chapter=0)

    response = client.put(
        f"/api/v1/documents/{alice['id']}/position", json={"sentence_id": foreign_sentence}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "sentence_not_in_document"
    assert client.get(f"/api/v1/documents/{alice['id']}").json()["reading_position"] is None


def test_unknown_sentence_is_rejected(client: TestClient, alice: dict) -> None:
    response = client.put(
        f"/api/v1/documents/{alice['id']}/position", json={"sentence_id": 999_999}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "sentence_not_in_document"


def test_document_with_a_reading_position_can_be_deleted(client: TestClient, alice: dict) -> None:
    url = f"/api/v1/documents/{alice['id']}"
    client.put(f"{url}/position", json={"sentence_id": sentence_id_in(client, alice["id"], 1)})

    assert client.delete(url).status_code == 204
