# Ficheiros de teste

Só entram aqui obras em domínio público (regra fixa 12 do `CLAUDE.md`).

| Ficheiro | Obra | Origem |
| --- | --- | --- |
| `pg11-alice.epub` | *Alice's Adventures in Wonderland*, Lewis Carroll (1865) | [Project Gutenberg, eBook n.º 11](https://www.gutenberg.org/ebooks/11), versão EPUB sem imagens, descarregada a 2026-11-11 |

O ficheiro está tal como foi descarregado, sem alterações, e inclui a licença do Project Gutenberg, que permite a redistribuição gratuita nessas condições. Lewis Carroll morreu em 1898, por isso a obra está em domínio público em Portugal e nos Estados Unidos.

Os testes dependem do conteúdo exato deste ficheiro (número de capítulos, títulos, uma frase conhecida). Se o substituíres por uma versão mais recente, é provável que tenhas de ajustar `test_import_service.py`.

Os EPUBs estragados ou maliciosos usados nos testes de validação não estão aqui: são gerados em memória por `tests/epub_factory.py`.
