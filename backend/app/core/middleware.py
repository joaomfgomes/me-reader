"""Middlewares: código que corre à volta de todos os pedidos.

Estão escritos como middlewares ASGI "puros". ASGI é o protocolo entre o
servidor (uvicorn) e a aplicação: cada pedido chega como uma chamada
app(scope, receive, send), em que "scope" descreve o pedido, "receive" lê o
corpo e "send" envia a resposta. Um middleware é uma app que embrulha outra.
"""

import logging
import time
import traceback
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import problem_response
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

# Nomes pelos quais o browser pode chegar legitimamente a esta app.
ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1"})


class HostValidationMiddleware:
    """Rejeita pedidos cujo cabeçalho Host não seja localhost ou 127.0.0.1.

    Escutar só em 127.0.0.1 não chega. Num ataque de "DNS rebinding", um site
    malicioso faz o seu próprio domínio (evil.example) resolver para 127.0.0.1;
    o browser julga que está a falar com esse site e deixa a página ler as
    respostas da nossa API. Nesse caso, porém, o cabeçalho Host diz
    "evil.example", e é isso que nos permite distinguir e recusar.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        host = Headers(scope=scope).get("host", "")
        # "localhost:8000" passa a "localhost". A porta não interessa: o pedido
        # tanto pode vir direto (8000) como pelo proxy do Vite (5173).
        hostname = host.split(":")[0].lower()
        if hostname not in ALLOWED_HOSTNAMES:
            response = problem_response(
                400,
                "invalid_host",
                "Cabeçalho Host inválido",
                "Esta aplicação só aceita pedidos feitos a localhost ou 127.0.0.1.",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Dá um identificador a cada pedido, regista-o nos logs e trata erros inesperados."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            # A resposta sai em várias mensagens. A primeira leva o estado e os
            # cabeçalhos, e é nela que juntamos o X-Request-ID. Com esse valor,
            # quem vê um erro no browser encontra as linhas certas no log.
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            # Último recurso para erros que ninguém tratou. Registamos o tipo e
            # o sítio do erro, mas não a mensagem da exceção: pode conter texto
            # de um documento (regra fixa 9).
            logger.error(
                "unhandled_error",
                extra={
                    "error_type": type(exc).__name__,
                    "traceback": "".join(traceback.format_tb(exc.__traceback__)),
                },
            )
            # Só podemos enviar a resposta de erro se ainda nada foi enviado.
            if not response_started:
                response = problem_response(
                    500,
                    "internal_error",
                    "Erro interno",
                    f"Erro inesperado. Procura o pedido {request_id} nos logs.",
                )
                await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    # Só o caminho, sem a query string, que pode levar texto.
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
                },
            )
            request_id_var.reset(token)
