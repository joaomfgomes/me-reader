"""Erros da API num formato único: application/problem+json (RFC 9457).

Todas as respostas de erro têm a mesma forma, e o frontend só precisa de saber
ler uma. O campo "code" é estável: o frontend decide o que mostrar com base
nele, e nós podemos melhorar o texto de "title" e "detail" sem partir nada.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"

# Código e título para os erros HTTP que o próprio framework gera.
_HTTP_ERRORS = {
    404: ("not_found", "Recurso não encontrado"),
    405: ("method_not_allowed", "Método não permitido"),
    413: ("file_too_large", "Ficheiro demasiado grande"),
}


def problem_response(
    status: int, code: str, title: str, detail: str | None = None, **extras: Any
) -> JSONResponse:
    """Constrói uma resposta de erro no formato da RFC 9457."""
    body: dict[str, Any] = {
        # "type" devia ser um URI com documentação do erro. Não temos essa
        # documentação, e a RFC manda usar "about:blank" nesse caso.
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail is not None:
        body["detail"] = detail
    # A RFC permite campos extra. Usamo-los, por exemplo, para o /health dizer
    # qual das verificações falhou.
    body.update(extras)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


class ProblemError(Exception):
    """Erro de aplicação que já sabe como se apresentar ao cliente.

    Qualquer módulo pode lançar esta exceção; o handler registado em baixo
    converte-a na resposta HTTP. Assim os módulos não precisam de conhecer HTTP
    para além do código de estado.
    """

    def __init__(
        self, status: int, code: str, title: str, detail: str | None = None, **extras: Any
    ) -> None:
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.extras = extras


def register_error_handlers(app: FastAPI) -> None:
    """Diz ao FastAPI como converter cada tipo de exceção em problem+json."""

    @app.exception_handler(ProblemError)
    async def _handle_problem(_request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.title, exc.detail, **exc.extras)

    # Erros HTTP gerados pelo framework, como o 404 de uma rota que não existe.
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = _HTTP_ERRORS.get(exc.status_code, ("http_error", "Erro HTTP"))
        return problem_response(exc.status_code, code, title)

    # Pedido que não passa na validação do Pydantic (campo em falta, tipo errado).
    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Devolvemos onde está o erro e porquê, mas não o valor recebido: pode
        # ser texto de um documento e não deve circular em erros nem em logs.
        errors = [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return problem_response(
            422,
            "validation_error",
            "Pedido inválido",
            "Um ou mais campos do pedido não são válidos.",
            errors=errors,
        )

    # As exceções inesperadas (erros 500) são tratadas no RequestContextMiddleware,
    # que está por fora de tudo e consegue juntar o identificador do pedido.
