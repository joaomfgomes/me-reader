# ADR-004: Cache imutável por hash de conteúdo

- **Estado:** aceite (2026-11-11)
- **Data:** 2026-11-11

## Contexto

Áudio e respostas do tutor custam dinheiro e são determinados pelo texto de entrada.

## Decisão

A chave de cache é um hash do texto mais os parâmetros que mudam o resultado:

- **Áudio:** texto do bloco, voz e versão do processo de limpeza.
- **Tutor:** frase, palavra ou seleção, tipo de pedido, modelo e versão do prompt.

As entradas nunca são alteradas, só criadas ou apagadas. A velocidade de leitura não entra na chave: é aplicada no browser sobre o mesmo ficheiro.

## Alternativa considerada

Cache com validade temporal. Rejeitada: o resultado não envelhece, só muda quando a entrada muda.

## Consequências

- Nada é pago duas vezes.
- Reimportar o mesmo livro reaproveita tudo.
- Corrigir a limpeza de texto invalida o áudio desses blocos.

## Rever quando

O espaço em disco for um problema, ou existir cache partilhada entre utilizadores.
