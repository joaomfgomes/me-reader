# Leitor de línguas

Leitor pessoal de EPUB e PDF que lê em voz alta, destaca cada palavra à medida que é dita e explica em português de Portugal o que o utilizador não percebe. Serve para aprender inglês, espanhol, francês, alemão e italiano com material autêntico. Uso pessoal, a correr em macOS, sem contas nem pagamentos.

A arquitetura completa está em `docs/arquitetura.md` e as decisões em `docs/adr/`. Lê esses ficheiros antes de qualquer alteração estrutural. Se uma tarefa obrigar a contrariar um ADR, pára e pergunta.

## Fase em curso

**Fase 1 em curso, dividida em três entregas.** Atualiza esta secção no fim de cada fase.

1. Importação e modelo de dados: feita (2026-11-11).
2. API: rotas `/documents` e posição de leitura. Feita (2026-11-11).
3. Frontend: biblioteca e leitor. Por fazer.

Cada entrega tem o seu plano e a sua aprovação; não avances para a seguinte sem pedido explícito.

O que existe da Fase 0: backend FastAPI com `GET /api/v1/health`, SQLite em modo WAL, validação do cabeçalho Host, erros em `problem+json`, logs JSON com identificador por pedido, e um frontend com uma página de estado.

O que existe da Fase 1:

- `importing/`: `import_epub(session, storage, data)` em `service.py` valida o ficheiro, extrai o texto, deteta a língua, segmenta e grava.
- `api/documents.py`: `POST /documents` (upload multipart, campo `file`), `GET /documents` (cursor), `GET`/`PATCH`/`DELETE /documents/{id}`, `GET /documents/{id}/chapters/{position}` (posição a começar em 0) e `PUT /documents/{id}/position`. As formas dos pedidos e respostas estão em `api/schemas.py`.
- Tabela `reading_positions` (migração `0003`), uma linha por documento.
- `BodySizeLimitMiddleware` corta pedidos acima do limite de upload sem os ler até ao fim.
- Tabelas `documents`, `chapters`, `blocks` e `sentences` (modelos em `importing/models.py`, migração `0002`). As posições de frases e palavras são índices no texto do bloco.
- `storage/`: interface `FileStorage` e implementação `DiskStorage`, em `data/files/`.
- `core/backup.py`: cópia da base de dados para `data/backups/` antes de migrações pendentes, guardando as últimas sete.

Os módulos `audio`, `tutor`, `vocabulary`, `providers` e `usage` estão vazios.

Convenções a manter:

- Colunas de data usam `UtcDateTime` (em `core/db.py`), nunca `DateTime` diretamente: o SQLite devolve datas sem fuso e a API tem de as mostrar sempre em UTC.
- As rotas são `def` (não `async def`) e recebem a sessão e o armazenamento por `SessionDep` e `StorageDep` (em `api/deps.py`).
- Erros de negócio lançam `ProblemError` com um `code` estável.

Por decidir ou por fazer mais tarde:

- A importação é síncrona e a resposta traz `status: "ready"`. Não há tabela de jobs; rever se a importação de PDF (Fase 5) for lenta.
- Mudar a língua de um documento não volta a dividir as frases.

- Os títulos dos capítulos ficam também como primeiro parágrafo do texto; o leitor (entrega 3) decide como os mostrar.
- As palavras são separadas pela mesma regra nas cinco línguas. Em francês e italiano, "l'homme" conta como uma palavra; rever na Fase 3, quando se carregar em palavras.
- A cópia diária da base de dados prevista na arquitetura não está feita; só a que antecede as migrações.

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
- **Texto:** leitura direta do ZIP com `zipfile` + defusedxml + BeautifulSoup (EPUB), pypdf ou pdfplumber (PDF), pySBD (frases), lingua (deteção de língua).
- **Voz:** Azure AI Speech, vozes Neural, com os tempos por palavra devolvidos pelo serviço.
- **Tutor:** LLM de baixo custo, com saída JSON validada por Pydantic.
- **Qualidade:** ruff, pytest, Vitest, gitleaks, GitHub Actions.

Não uses PyMuPDF nem EbookLib (licença AGPL); confirma a licença de qualquer dependência nova antes de a acrescentar. Não acrescentes Redis, filas, Docker, Postgres nem autenticação nesta fase.

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
data/             base de dados, files/ (originais e áudio), backups/ e logs/; fora do git
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
- Confirmar que modelos e migrações coincidem: `cd backend && uv run alembic check`.
- Todas as verificações de pre-commit: `cd backend && uv run pre-commit run --all-files`.

Os testes do backend criam a aplicação com `create_app(settings)` e uma pasta de dados temporária (ver `backend/tests/conftest.py`). O `TestClient` tem de usar `base_url="http://localhost"`, senão a validação do Host rejeita os pedidos. EPUBs de teste estragados ou maliciosos geram-se com `tests/epub_factory.py`; o livro real está em `backend/tests/fixtures/`.

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
