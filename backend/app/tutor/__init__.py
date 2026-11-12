"""Tutor de palavras e frases (Fases 3 e 4).

Monta prompts versionados com o contexto, chama o LLM através da interface própria,
valida o JSON da resposta com Pydantic e guarda-a em cache.

Por onde começar a ler: tutor.py (a interface e o formato da resposta), service.py
(o fluxo) e prompts/ (o que é pedido ao modelo).
"""
