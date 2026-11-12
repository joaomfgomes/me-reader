# Leitor de línguas

Leitor pessoal de EPUB e PDF que lê em voz alta, destaca cada palavra à medida que é dita e explica em português de Portugal o que não percebes. Serve para aprender inglês, espanhol, francês, alemão e italiano com material autêntico.

Corre só no teu Mac, como app web local, sem contas nem pagamentos.

## Estado

**Fase 2 (áudio com destaque) concluída.** Importas um EPUB, lê-lo e ouve-lo com a palavra em curso destacada. Podes mudar a velocidade, saltar entre frases, ver quanto custaria o áudio antes de o gerar e consultar o consumo do mês na página "Custos". O áudio fica guardado: ouvir o mesmo texto outra vez não custa nada. A seguir vem o tutor, que explica palavras em português.

Sem configuração, a voz é simulada (um bip por palavra, sem chamadas externas). Para ouvir uma voz verdadeira, vê "Voz com o Azure" mais abaixo.

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
5. Abre <http://127.0.0.1:5173> no browser. Deves ver a biblioteca vazia e, no rodapé, "Sistema saudável".
6. Carrega em "Importar EPUB" e escolhe um livro. Para experimentar, há um em `backend/tests/fixtures/pg11-alice.epub`.

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
| `make voice-check` | Testa o fornecedor de voz configurado, com chamadas verdadeiras |

## Configuração

A configuração vive no ficheiro `.env`, criado a partir do [.env.example](.env.example). O `.env` nunca entra no git.

| Variável | Valor por omissão | Para que serve |
| --- | --- | --- |
| `READER_DATA_DIR` | `./data` | Pasta da base de dados, dos originais, do áudio e dos logs |
| `READER_PORT` | `8000` | Porta do backend |
| `READER_LOG_LEVEL` | `INFO` | Nível de detalhe dos logs |
| `READER_SPEECH_PROVIDER` | `fake` | Fornecedor de voz: `fake` (simulado, sem custos) ou `azure` |
| `AZURE_SPEECH_KEY` | vazio | Chave do recurso Azure AI Speech |
| `AZURE_SPEECH_REGION` | vazio | Região do recurso, por exemplo `westeurope` |
| `READER_MONTHLY_TTS_CHAR_LIMIT` | `500000` | Teto mensal de caracteres enviados ao serviço de voz |
| `READER_TTS_USD_PER_MILLION_CHARS` | `16` | Preço usado para estimar custos |

## Voz com o Azure

1. No portal do Azure, cria um recurso "Speech" no escalão gratuito F0, que dá 500 000 caracteres por mês em vozes Neural e não acumula custos.
2. Copia a chave e a região do recurso para o `.env`, em `AZURE_SPEECH_KEY` e `AZURE_SPEECH_REGION`, e põe `READER_SPEECH_PROVIDER=azure`.
3. Confirma que funciona com `make voice-check`, que sintetiza uma frase por língua (cerca de 400 caracteres da quota).

O texto de cada excerto que ouves pela primeira vez é enviado ao Azure. Nos documentos marcados como privados, a aplicação pede confirmação antes do primeiro envio. O teto mensal da aplicação (`READER_MONTHLY_TTS_CHAR_LIMIT`) impede que passes o escalão gratuito sem dar por isso.

## Onde está cada coisa

```
backend/app/core/        configuração, base de dados, logs, erros, middlewares
backend/app/api/         rotas /api/v1
backend/app/importing/   validação, extração, limpeza e segmentação de EPUB
backend/app/storage/     interface de armazenamento de ficheiros (hoje disco)
backend/app/audio/       cache de áudio, alinhamento de tempos e estimativa de custo
backend/app/providers/   fornecedores externos: voz simulada e Azure AI Speech
backend/app/usage/       registo de consumo e teto mensal
backend/app/<módulo>/    tutor, vocabulary (ainda vazios)
backend/migrations/      migrações Alembic
backend/tests/           testes do backend
frontend/src/pages/      biblioteca, leitor e custos
frontend/src/reader/     texto do capítulo e leitor de áudio
frontend/src/api/        chamadas ao backend
frontend/src/lib/        preferências e textos da interface
data/                    base de dados, ficheiros, cópias de segurança e logs; fora do git
```

Com a app a correr, a documentação interativa da API está em <http://127.0.0.1:8000/docs>.

## Segurança

- O servidor escuta apenas em `127.0.0.1` e rejeita pedidos cujo cabeçalho `Host` não seja `localhost` ou `127.0.0.1`.
- Não há CORS aberto: o frontend chega ao backend pelo proxy do Vite.
- Pedidos que alteram dados são recusados se vierem de uma página de outro site (cabeçalho `Origin`).
- Os ficheiros importados são validados antes de serem lidos: tamanho, tipo pelo conteúdo e estrutura do ZIP. O HTML dos livros nunca é mostrado; a app extrai só o texto.
- O gitleaks corre antes de cada commit e no GitHub Actions, para nenhuma chave entrar no repositório.
- Os logs (em `data/logs/app.log`) levam identificadores e durações, nunca chaves nem texto dos documentos.

## Logs

Cada linha do log é um objeto JSON com o identificador do pedido, que também é devolvido no cabeçalho `X-Request-ID` de cada resposta. Para ver os pedidos com erro:

```bash
grep '"message": "request"' data/logs/app.log | grep -v '"status": 200'
```
