"""Arranca o servidor: "python -m app" (ou "python -m app --reload" em desenvolvimento)."""

import argparse

import uvicorn

from app.core.config import SERVER_HOST, Settings
from app.core.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor do Leitor de línguas")
    parser.add_argument(
        "--reload", action="store_true", help="reinicia o servidor quando o código muda"
    )
    args = parser.parse_args()

    settings = Settings()
    configure_logging(settings.log_level)

    uvicorn.run(
        # Passamos o caminho da fábrica em texto, e não a app já criada, porque
        # o modo --reload precisa de a voltar a importar a cada alteração.
        "app.main:create_app",
        factory=True,
        host=SERVER_HOST,
        port=settings.port,
        reload=args.reload,
        # Desligamos a configuração de logs do uvicorn para as mensagens dele
        # passarem pelo nosso formatador JSON, e o log de acessos dele porque
        # o RequestContextMiddleware já regista cada pedido.
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
