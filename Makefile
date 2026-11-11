# Comandos do dia a dia. Corre "make" sem argumentos para ver a lista.
#
# .PHONY diz ao make que estes nomes são comandos e não ficheiros a construir.
.PHONY: help setup dev dev-backend dev-frontend migrate test lint format

help:
	@echo "make setup    instala dependências, cria o .env e ativa o pre-commit"
	@echo "make dev      aplica migrações e arranca backend e frontend"
	@echo "make test     corre os testes do backend e do frontend"
	@echo "make lint     verifica estilo, erros comuns e tipos"
	@echo "make format   formata o código Python"
	@echo "make migrate  aplica as migrações em falta à base de dados"

setup:
	cd backend && uv sync
	cd frontend && pnpm install
	@# Cria o .env a partir do modelo, mas só se ainda não existir.
	test -f .env || cp .env.example .env
	@# Instala o hook do git que corre o gitleaks e o ruff antes de cada commit.
	cd backend && uv run pre-commit install

migrate:
	cd backend && uv run alembic upgrade head

# "dev" depende de "migrate": a base de dados fica sempre na última versão
# antes de os servidores arrancarem. O -j2 corre os dois alvos em paralelo;
# Ctrl+C pára ambos.
dev: migrate
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uv run python -m app --reload

dev-frontend:
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd frontend && pnpm typecheck

format:
	cd backend && uv run ruff check --fix .
	cd backend && uv run ruff format .
