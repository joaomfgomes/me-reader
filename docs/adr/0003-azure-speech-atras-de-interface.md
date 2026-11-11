# ADR-003: Azure AI Speech atrás de uma interface de voz

- **Estado:** aceite (2026-11-11)
- **Data:** 2026-11-11

## Contexto

O destaque palavra a palavra exige tempos por palavra em inglês, espanhol, francês, alemão e italiano. O escalão gratuito do Azure dá 0,5 milhões de caracteres por mês em vozes Neural, cerca de um livro.

## Decisão

Usar vozes Neural do Azure e os tempos que o serviço devolve. Todo o código do fornecedor fica num único módulo (`providers/`) que implementa uma interface de voz própria. O mapeamento entre tempos e palavras faz-se pelos offsets de texto devolvidos pelo Azure, não pela contagem de palavras.

## Alternativa considerada

Modelo local (Kokoro) com alinhamento forçado. Gratuito e privado, mas só dá tempos por palavra em inglês.

## Consequências

- Sem cálculo de alinhamento próprio.
- Dependência de rede e de preço por carácter.
- Trocar de fornecedor é implementar a interface noutro módulo.

## Rever quando

O consumo passar o escalão gratuito com regularidade, ou um modelo local der tempos por palavra nas cinco línguas.
