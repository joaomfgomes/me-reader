"""Junta todas as rotas da API debaixo do prefixo /api/v1."""

from fastapi import APIRouter

from app.api import health

# O número da versão vai no caminho. Uma mudança incompatível cria /api/v2 e as
# duas versões convivem enquanto for preciso; acrescentar campos opcionais não
# obriga a versão nova.
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
