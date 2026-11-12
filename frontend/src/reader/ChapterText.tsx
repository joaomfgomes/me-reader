import { memo, type MouseEvent, type ReactNode } from "react";

import type { Block, ChapterDetail, Sentence } from "../api/documents";

// Altura da barra fixa no topo. Uma frase só conta como "visível" abaixo dela.
export const HEADER_OFFSET_PX = 72;

/** Identifica o elemento de uma palavra: o bloco e a posição dela no texto do bloco. */
export function wordKey(blockId: number, start: number): string {
  return `${blockId}-${start}`;
}

/** Agrupa as frases de um bloco por parágrafo, usando os "\n" do texto. */
function paragraphsOf(block: Block): Sentence[][] {
  const paragraphs: Sentence[][] = [];
  let current: Sentence[] = [];
  let paragraphEnd = block.text.indexOf("\n");
  for (const sentence of block.sentences) {
    // Uma frase que começa depois da quebra pertence ao parágrafo seguinte.
    while (paragraphEnd !== -1 && sentence.start_offset > paragraphEnd) {
      paragraphs.push(current);
      current = [];
      paragraphEnd = block.text.indexOf("\n", paragraphEnd + 1);
    }
    current.push(sentence);
  }
  paragraphs.push(current);
  return paragraphs.filter((paragraph) => paragraph.length > 0);
}

/**
 * O texto de uma frase, com cada palavra no seu elemento.
 *
 * As posições das palavras vêm da importação. Entre duas palavras fica o
 * texto que as separa (espaços e pontuação), tal como está.
 */
function sentencePieces(block: Block, sentence: Sentence): ReactNode[] {
  const pieces: ReactNode[] = [];
  let cursor = sentence.start_offset;
  for (const [start, end] of sentence.words) {
    if (start > cursor) {
      pieces.push(block.text.slice(cursor, start));
    }
    pieces.push(
      <span key={start} data-word-key={wordKey(block.id, start)}>
        {block.text.slice(start, end)}
      </span>,
    );
    cursor = end;
  }
  if (cursor < sentence.end_offset) {
    pieces.push(block.text.slice(cursor, sentence.end_offset));
  }
  return pieces;
}

interface ChapterTextProps {
  chapter: ChapterDetail;
  /** A frase onde o leitor parou, passada a marcador ao abrir o livro. */
  markedSentenceId: number | null;
  /** A frase que está a ser lida em voz alta. */
  activeSentenceId: number | null;
  onSentenceClick: (sentenceId: number) => void;
}

/**
 * O texto de um capítulo.
 *
 * "memo" evita redesenhar os milhares de elementos do capítulo quando muda
 * algo que não lhe diz respeito (o estado do leitor de áudio, por exemplo):
 * o React só volta a desenhar este componente se uma das props mudar.
 *
 * A palavra que está a ser dita NÃO passa por aqui. Muda várias vezes por
 * segundo, por isso o leitor de áudio acende-a diretamente no elemento, sem
 * envolver o React (ver useAudioPlayer).
 */
export const ChapterText = memo(function ChapterText({
  chapter,
  markedSentenceId,
  activeSentenceId,
  onSentenceClick,
}: ChapterTextProps) {
  // Um só "ouvinte" de cliques para o capítulo inteiro, em vez de um por
  // frase: o clique sobe pela árvore e aqui procuramos a frase onde caiu.
  function handleClick(event: MouseEvent<HTMLDivElement>) {
    // Se o utilizador acabou de selecionar texto com o rato, não é um clique.
    if (!window.getSelection()?.isCollapsed) {
      return;
    }
    const sentence = (event.target as HTMLElement).closest<HTMLElement>("[data-sentence-id]");
    if (sentence) {
      onSentenceClick(Number(sentence.dataset.sentenceId));
    }
  }

  // O primeiro parágrafo de um capítulo costuma ser o seu título.
  let titleShown = false;

  return (
    <div onClick={handleClick}>
      {chapter.blocks.map((block) =>
        paragraphsOf(block).map((sentences) => {
          const text = sentences.map((sentence) => sentence.text).join(" ");
          const isTitle = !titleShown && text === chapter.title;
          titleShown = true;
          const content = sentences.map((sentence, index) => {
            const className =
              sentence.id === activeSentenceId
                ? "sentence-now"
                : sentence.id === markedSentenceId
                  ? "marked"
                  : undefined;
            return (
              <span key={sentence.id}>
                {index > 0 && " "}
                <span
                  data-sentence-id={sentence.id}
                  className={`cursor-pointer ${className ?? ""}`}
                  // Ao saltar para uma frase, deixa-a abaixo da barra fixa.
                  style={{ scrollMarginTop: HEADER_OFFSET_PX + 16 }}
                >
                  {sentencePieces(block, sentence)}
                </span>
              </span>
            );
          });
          return isTitle ? (
            <h1
              key={sentences[0].id}
              className="mb-[1.2em] text-[1.6em] leading-tight font-semibold"
            >
              {content}
            </h1>
          ) : (
            <p key={sentences[0].id} className="mt-[0.85em]">
              {content}
            </p>
          );
        }),
      )}
    </div>
  );
});
