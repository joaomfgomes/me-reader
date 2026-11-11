# Leitor de línguas

Leitor pessoal de EPUB e PDF que lê em voz alta, destaca cada palavra à medida que é dita e explica em português de Portugal o que o utilizador não percebe. Serve para aprender inglês, espanhol, francês, alemão e italiano com material autêntico. Uso pessoal, a correr em macOS, sem contas nem pagamentos.

A arquitetura completa está em `docs/arquitetura.md` e as decisões em `docs/adr/`. Lê esses ficheiros antes de qualquer alteração estrutural. Se uma tarefa obrigar a contrariar um ADR, pára e pergunta.

## Fase em curso

**Fase 0 concluída (2026-11-11). A seguinte é a Fase 1, importar e ler EPUB, que só começa com pedido explícito.** Atualiza esta secção no fim de cada fase.

O que existe: backend FastAPI com `GET /api/v1/health`, SQLite em modo WAL com uma migração inicial (tabela `app_meta`), validação do cabeçalho Host, erros em `problem+json`, logs JSON com identificador por pedido, e um frontend com uma página de estado. Os módulos `importing`, `audio`, `tutor`, `vocabulary`, `storage`, `providers` e `usage` estão vazios.

Adiado da Fase 0 para a Fase 1: a cópia automática da base de dados antes das migrações (prevista em `docs/arquitetura.md`), porque ainda não há dados para proteger.

Fases (detalhe em `docs/arquitetura.md`, secção "Plano, MVP e riscos"):

0. Esqueleto: repositório, backend e frontend a arrancar, `/health`, migrações, segredos, lint e testes em CI.
1. Importar e ler EPUB, sem chamadas externas.
2. Áudio com destaque palavra a palavra, cache, página "Custos".
3. Tutor de palavra, com cache e palavras guardadas.
4. Tutor de frase e revisão com repetição espaçada.
5. PDF com texto e marca "privado".

O MVP são as fases 0 a 3. Implementa uma fase de cada vez e não avances para a seguinte sem pedido explícito.

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite em modo WAL. Gestão com `uv`.
- **Frontend:** React, Vite, TypeScript, TanStack Query, Tailwind. Gestão com `pnpm`.
- **Texto:** EbookLib + BeautifulSoup (EPUB), pypdf ou pdfplumber (PDF), pySBD (frases), lingua (deteção de língua).
- **Voz:** Azure AI Speech, vozes Neural, com os tempos por palavra devolvidos pelo serviço.
- **Tutor:** LLM de baixo custo, com saída JSON validada por Pydantic.
- **Qualidade:** ruff, pytest, Vitest, gitleaks, GitHub Actions.

Não uses PyMuPDF (licença AGPL). Não acrescentes Redis, filas, Docker, Postgres nem autenticação nesta fase.

## Estrutura prevista

```
backend/
  app/
    core/         configuração, base de dados, logs, erros e middlewares
    api/          rotas /api/v1
    importing/    extração, limpeza e segmentação de EPUB e PDF
    audio/        cache, síntese, tempos por palavra, estimativa de custo
    tutor/        prompts versionados, chamada ao LLM, validação
    vocabulary/   vocabulário e repetição espaçada
    storage/      interface de armazenamento (hoje disco)
    providers/    único sítio com código do Azure e do fornecedor de LLM
    usage/        registo de consumo e teto mensal
  migrations/     Alembic
  tests/
frontend/
  src/
docs/
  arquitetura.md
  adr/
data/             base de dados, originais e áudio; fora do git
```

## Comandos

Correm todos na raiz do repositório.

- `make setup`: instala dependências (`uv sync`, `pnpm install`), cria o `.env` e ativa o pre-commit.
- `make dev`: aplica as migrações e arranca o backend em `127.0.0.1:8000` e o frontend em `127.0.0.1:5173`.
- `make test`: pytest no backend e Vitest no frontend.
- `make lint`: `ruff check`, `ruff format --check` e `tsc --noEmit`.
- `make format`: corrige e formata o código Python com ruff.
- `make migrate`: `alembic upgrade head`.

Comandos úteis fora do Makefile:

- Um só teste do backend: `cd backend && uv run pytest tests/test_health.py -k nome`.
- Nova migração: `cd backend && uv run alembic revision --autogenerate -m "descrição"`. Revê sempre o ficheiro gerado.
- Todas as verificações de pre-commit: `cd backend && uv run pre-commit run --all-files`.

Os testes do backend criam a aplicação com `create_app(settings)` e uma pasta de dados temporária (ver `backend/tests/conftest.py`). O `TestClient` tem de usar `base_url="http://localhost"`, senão a validação do Host rejeita os pedidos.

## Regras fixas

1. **Código comentado para aprender.** O autor tem nível inicial a intermédio em backend e full-stack. Comenta o porquê das decisões e os conceitos menos óbvios, em português de Portugal. Não comentes o óbvio.
2. **Nomes em inglês, texto em português.** Identificadores, rotas e nomes de ficheiros em inglês; comentários, documentação e texto da interface em pt-PT.
3. **Segredos fora do git.** Chaves só em `.env`, com `.env.example` atualizado. Nunca em código, logs, testes ou frontend.
4. **Fornecedores só em `providers/`.** O resto da app fala com interfaces próprias (voz, tutor, armazenamento), nunca com SDKs externos.
5. **Testes sem chaves reais.** Os fornecedores são simulados. Nenhum teste faz chamadas pagas.
6. **Cache por hash de conteúdo.** Áudio e respostas do tutor nunca são gerados duas vezes para a mesma entrada (ADR-004).
7. **Servidor só em 127.0.0.1**, com validação do cabeçalho Host e sem CORS aberto.
8. **Ficheiros importados não são de confiança.** Limites de tamanho, verificação de tipo pelo conteúdo, proteção contra caminhos maliciosos no ZIP, e o HTML do livro nunca é mostrado tal como vem.
9. **Logs sem conteúdo.** Nunca registes chaves nem texto dos documentos; só identificadores e tamanhos.
10. **SQL portável.** Nada específico de SQLite que impeça migrar para Postgres. Alterações de esquema só por migração Alembic.
11. **Erros da API em `application/problem+json`** (RFC 9457) com um `code` estável.
12. **Dados de teste em domínio público.** Nenhum livro com direitos de autor entra no repositório.

## Forma de trabalhar

- Antes de escrever código, apresenta o plano e a lista de ficheiros a criar ou alterar, e espera aprovação.
- Alterações pequenas e verificáveis; corre lint e testes antes de dar a tarefa por concluída.
- Se faltar informação, pergunta. Não inventes requisitos.
- No fim de cada fase: atualiza "Fase em curso" e "Comandos" neste ficheiro e o `README.md`.

## Decisões em aberto

- Fornecedor de LLM a usar primeiro (decidir antes da Fase 3).
- Recurso Azure AI Speech no escalão gratuito F0: confirmar que existe antes da Fase 2.
- ADR-001 e ADR-002 foram aceites a 2026-11-11. Os ADR-003, 004 e 005 continuam com estado "proposta" até o autor os aprovar (antes das Fases 2 e 3).
