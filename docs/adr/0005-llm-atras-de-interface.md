# ADR-005: LLM atrás de interface, com saída JSON validada e prompts versionados

- **Estado:** proposta
- **Data:** 2026-11-11

## Contexto

Os modelos baratos mudam de preço e de nome com frequência. A interface precisa de campos fixos (lema, classe gramatical, tradução, definição, IPA).

## Decisão

Uma interface de tutor com um método por tipo de pedido (palavra, traduzir, gramática, expressão, simplificar). Cada resposta é validada contra um esquema Pydantic. Os prompts vivem em ficheiros com número de versão. O fornecedor concreto fica em `providers/`.

## Alternativa considerada

Modelo local (Ollama). Privado, mas mais fraco em explicações em pt-PT.

## Consequências

- Trocar de modelo é mudar uma configuração e correr o conjunto de teste (20 frases por língua).
- Respostas inválidas nunca chegam ao ecrã nem à cache.
- O texto das frases consultadas sai do portátil.

## Rever quando

For precisa conversa livre com o documento, que pede outro padrão (pesquisa no texto e respostas em fluxo).
