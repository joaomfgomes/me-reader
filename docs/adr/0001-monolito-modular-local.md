# ADR-001: Monólito modular local

- **Estado:** proposta
- **Data:** 2026-11-11

## Contexto

Um utilizador, um Mac, um programador, projeto recreativo. A versão web multiutilizador é um cenário futuro, não um requisito atual.

## Decisão

Um processo FastAPI com módulos internos (importação, áudio, tutor, vocabulário, armazenamento, uso) e um frontend React servido em localhost. Frontend e backend comunicam por uma API HTTP versionada (`/api/v1`).

## Alternativa considerada

Serverless por função, ou microserviços. Rejeitados: acrescentam deploy, rede e monitorização sem resolver nenhum problema atual.

## Consequências

- Simples de correr, depurar e aprender.
- Não há escala horizontal nem isolamento entre módulos.
- As fronteiras entre módulos dependem de disciplina no código.

## Rever quando

Existir versão web com carga real que sature um módulo.
