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
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
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


# Métodos que só leem. Todos os outros alteram dados.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CrossSiteRequestMiddleware:
    """Recusa pedidos de escrita feitos por páginas de outros sites (CSRF).

    Sem CORS, o browser não deixa outro site *ler* as nossas respostas, mas
    deixa-o *enviar* certos pedidos, como um formulário com um ficheiro. Uma
    página maliciosa aberta noutro separador podia assim importar documentos
    para a biblioteca sem o utilizador dar por isso. Nesses pedidos o browser
    envia sempre o cabeçalho Origin com o endereço da página que os fez, e é
    por ele que os distinguimos.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Sem Origin, o pedido não vem de uma página web (é o curl, por
        # exemplo) e não há terceiro a aproveitar-se do browser do utilizador.
        origin = Headers(scope=scope).get("origin")
        if origin is not None and urlsplit(origin).hostname not in ALLOWED_HOSTNAMES:
            response = problem_response(
                403,
                "cross_site_request",
                "Pedido de outro site recusado",
                "Esta aplicação só aceita alterações feitas a partir da sua própria página.",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Recusa pedidos cujo corpo ultrapasse um limite, sem o ler até ao fim.

    Sem isto, um upload de vários GB seria recebido e guardado por inteiro
    antes de a rota ter oportunidade de o recusar.
    """

    def __init__(self, app: ASGIApp, max_bytes: Callable[[], int]) -> None:
        self.app = app
        # Recebe uma função, e não um número, para o limite ser lido em cada
        # pedido. Assim os testes conseguem baixá-lo temporariamente.
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self._max_bytes()

        # Caso simples: o cliente declara o tamanho no cabeçalho Content-Length
        # e podemos recusar antes de receber um único byte do corpo.
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            response = problem_response(
                413, "file_too_large", "Ficheiro demasiado grande", "O pedido excede o limite."
            )
            await response(scope, receive, send)
            return

        # O Content-Length pode faltar (envio aos bocados) ou mentir, por isso
        # contamos também os bytes que vão chegando.
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    # Tem de ser uma HTTPException: é o único tipo de erro que
                    # o FastAPI deixa passar intacto enquanto lê o corpo do
                    # pedido. O handler em errors.py converte-a em problem+json.
                    raise HTTPException(status_code=413)
            return message

        await self.app(scope, limited_receive, send)


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
