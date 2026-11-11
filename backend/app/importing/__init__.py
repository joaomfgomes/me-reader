"""Importação de documentos (Fase 1 para EPUB, Fase 5 para PDF).

Valida o ficheiro, extrai e limpa o texto e divide-o em capítulos, blocos, frases e
palavras, detetando a língua. Não faz chamadas externas: nada sai do portátil aqui.

Por onde começar a ler: service.py (o fluxo completo), depois validation.py, epub.py,
cleaning.py, language.py e segmentation.py, pela ordem em que são chamados.
"""
