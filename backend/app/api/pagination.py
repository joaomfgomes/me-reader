"""Paginação por cursor, partilhada pelas rotas que devolvem listas."""

import base64
import binascii

from app.core.errors import ProblemError


def encode_cursor(last_id: int) -> str:
    # O cursor é o id do último elemento da página, disfarçado em base64 para
    # o cliente o tratar como um valor opaco e não fazer contas com ele.
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (binascii.Error, ValueError) as exc:
        raise ProblemError(
            422, "invalid_cursor", "Cursor inválido", "Usa o next_cursor da resposta anterior."
        ) from exc
