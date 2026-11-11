# ADR-002: SQLite e ficheiros em disco, com caminho para Postgres

- **Estado:** proposta
- **Data:** 2026-11-11

## Contexto

Os dados são pequenos e de um só utilizador; o áudio é grande e binário.

## Decisão

Metadados, tempos por palavra e caches de texto em SQLite (modo WAL). Originais e áudio em disco, atrás de uma interface de armazenamento. SQL portável via SQLAlchemy 2 e migrações Alembic.

## Alternativa considerada

Postgres desde o início. Rejeitado: obriga a correr um serviço sem ganho hoje.

## Consequências

- Backup por cópia de pasta e zero serviços a correr.
- Um só escritor de cada vez.
- Risco: SQL específico de SQLite dificultar a migração futura.

## Rever quando

Houver mais de um utilizador ou mais de uma instância do backend.
