# Leitor de línguas

Leitor pessoal de EPUB e PDF que lê em voz alta, destaca cada palavra à medida que é dita e explica em português de Portugal o que não percebes. Serve para aprender inglês, espanhol, francês, alemão e italiano com material autêntico.

Corre só no teu Mac, como app web local, sem contas nem pagamentos.

## Estado

**Fase 1 (importar e ler EPUB) em curso.** O backend já sabe importar um EPUB: valida o ficheiro, extrai o texto, deteta a língua e divide-o em capítulos, blocos, frases e palavras. Ainda não há forma de o fazer pela aplicação: as rotas da API, a biblioteca e o leitor são as próximas entregas. A página inicial mostra apenas o estado do sistema.

O plano completo está em [docs/arquitetura.md](docs/arquitetura.md) e as decisões em [docs/adr/](docs/adr/).

## Instalação

Precisas de macOS com [Homebrew](https://brew.sh), git e Node.js 24 ou superior.

1. Instala as ferramentas de gestão de dependências:
   ```bash
   brew install uv pnpm
   ```
2. Clona o repositório e entra na pasta.
3. Instala as dependências, cria o `.env` e ativa as verificações de pre-commit:
   ```bash
   make setup
   ```
4. Arranca a aplicação:
   ```bash
   make dev
   ```
5. Abre <http://127.0.0.1:5173> no browser. Deves ver "Sistema saudável".

O `uv` instala sozinho o Python 3.12. O `make dev` aplica as migrações da base de dados antes de arrancar, e `Ctrl+C` pára os dois servidores.

## Comandos

| Comando | O que faz |
| --- | --- |
| `make setup` | Instala dependências, cria o `.env` e ativa o pre-commit |
| `make dev` | Aplica migrações e arranca o backend (porta 8000) e o frontend (porta 5173) |
| `make test` | Corre os testes do backend (pytest) e do frontend (Vitest) |
| `make lint` | Verifica o código com ruff e os tipos com TypeScript |
| `make format` | Formata o código Python |
| `make migrate` | Copia a base de dados para `data/backups/` e aplica as migrações em falta |

## Configuração

A configuração vive no ficheiro `.env`, criado a partir do [.env.example](.env.example). O `.env` nunca entra no git.

| Variável | Valor por omissão | Para que serve |
| --- | --- | --- |
| `READER_DATA_DIR` | `./data` | Pasta da base de dados, dos originais, do áudio e dos logs |
| `READER_PORT` | `8000` | Porta do backend |
| `READER_LOG_LEVEL` | `INFO` | Nível de detalhe dos logs |

## Onde está cada coisa

```
backend/app/core/        configuração, base de dados, logs, erros, middlewares
backend/app/api/         rotas /api/v1
backend/app/importing/   validação, extração, limpeza e segmentação de EPUB
backend/app/storage/     interface de armazenamento de ficheiros (hoje disco)
backend/app/<módulo>/    audio, tutor, vocabulary, providers, usage (ainda vazios)
backend/migrations/      migrações Alembic
backend/tests/           testes do backend
frontend/src/            aplicação React
data/                    base de dados, ficheiros, cópias de segurança e logs; fora do git
```

Com a app a correr, a documentação interativa da API está em <http://127.0.0.1:8000/docs>.

## Segurança

- O servidor escuta apenas em `127.0.0.1` e rejeita pedidos cujo cabeçalho `Host` não seja `localhost` ou `127.0.0.1`.
- Não há CORS aberto: o frontend chega ao backend pelo proxy do Vite.
- O gitleaks corre antes de cada commit e no GitHub Actions, para nenhuma chave entrar no repositório.
- Os logs (em `data/logs/app.log`) levam identificadores e durações, nunca chaves nem texto dos documentos.

## Logs

Cada linha do log é um objeto JSON com o identificador do pedido, que também é devolvido no cabeçalho `X-Request-ID` de cada resposta. Para ver os pedidos com erro:

```bash
grep '"message": "request"' data/logs/app.log | grep -v '"status": 200'
```
