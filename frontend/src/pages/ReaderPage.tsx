import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import {
  getChapter,
  getDocument,
  savePosition,
  type ChapterSummary,
  type DocumentDetail,
} from "../api/documents";
import { errorMessage } from "../lib/messages";
import { FONT_SIZE_MAX, FONT_SIZE_MIN, FONT_SIZE_STEP, usePreferences } from "../lib/preferences";
import { ChapterText, HEADER_OFFSET_PX } from "../reader/ChapterText";
import { PlayerBar } from "../reader/PlayerBar";
import { useAudioPlayer } from "../reader/useAudioPlayer";

// Tempo de espera depois do último movimento antes de guardar a posição.
// Evita fazer um pedido por cada píxel de scroll.
export const SAVE_DELAY_MS = 700;

function chapterLabel(chapter: ChapterSummary): string {
  return chapter.title ?? `Parte ${chapter.position + 1}`;
}

/** A primeira frase visível abaixo da barra do topo, ou a primeira do capítulo. */
function firstVisibleSentenceId(container: HTMLElement): number | null {
  const sentences = container.querySelectorAll<HTMLElement>("[data-sentence-id]");
  for (const element of sentences) {
    if (element.getBoundingClientRect().bottom > HEADER_OFFSET_PX) {
      return Number(element.dataset.sentenceId);
    }
  }
  return sentences[0] ? Number(sentences[0].dataset.sentenceId) : null;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function ReaderPage() {
  const documentId = Number(useParams().id);
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { preferences, changeFontSize } = usePreferences();

  const documentKey = ["document", documentId];
  const documentQuery = useQuery({
    queryKey: documentKey,
    queryFn: () => getDocument(documentId),
  });
  const document = documentQuery.data;

  // A posição com que o livro foi aberto. Fica fixa durante a visita: é para
  // lá que saltamos uma vez e é essa frase que aparece marcada. Um "ref"
  // guarda um valor entre renderizações sem provocar uma nova.
  const [resume, setResume] = useState<{ chapter: number; sentenceId: number } | null>(null);
  const resumeDecided = useRef(false);
  useEffect(() => {
    if (document && !resumeDecided.current) {
      resumeDecided.current = true;
      const saved = document.reading_position;
      if (saved) {
        setResume({ chapter: saved.chapter_position, sentenceId: saved.sentence_id });
      }
    }
  }, [document]);

  // O capítulo vem do endereço (?c=3), o que faz os botões de recuar e avançar
  // do browser funcionarem. Sem ele, abrimos onde o leitor parou.
  const requested = searchParams.get("c");
  const chapterPosition =
    requested !== null ? Number(requested) : (document?.reading_position?.chapter_position ?? 0);

  const chapterQuery = useQuery({
    queryKey: ["chapter", documentId, chapterPosition],
    queryFn: () => getChapter(documentId, chapterPosition),
    // Só pedimos o capítulo depois de sabermos qual é.
    enabled: document !== undefined,
  });
  const chapter = chapterQuery.data;

  const lastSaved = useRef<number | null>(null);
  const save = useMutation({
    mutationFn: (sentenceId: number) => savePosition(documentId, sentenceId),
    onSuccess: (position) => {
      // Atualiza o documento em cache com a nova posição, para a próxima
      // visita a este livro abrir no sítio certo sem novo pedido.
      queryClient.setQueryData<DocumentDetail>(documentKey, (current) =>
        current ? { ...current, reading_position: position } : current,
      );
    },
  });
  const saveSentence = useCallback(
    (sentenceId: number) => {
      if (sentenceId !== lastSaved.current) {
        lastSaved.current = sentenceId;
        save.mutate(sentenceId);
      }
    },
    // "save" muda a cada pedido; a função mutate em si é sempre a mesma.
    [save.mutate],
  );

  const article = useRef<HTMLElement>(null);
  // A frase a marcar e para onde saltar, se este for o capítulo onde o leitor parou.
  const resumeSentenceId =
    resume !== null && resume.chapter === chapterPosition ? resume.sentenceId : null;
  const jumped = useRef(false);

  const player = useAudioPlayer({
    documentId,
    chapter,
    playbackRate: preferences.playbackRate,
    container: article,
    // "Ouvir" começa na frase onde o leitor parou ou, se já andou pela
    // página, na primeira frase que tem à frente.
    getStartSentenceId: () =>
      (window.scrollY === 0 ? resumeSentenceId : null) ??
      (article.current ? firstVisibleSentenceId(article.current) : null),
  });
  const audioActive = player.status === "playing" || player.status === "loading";
  // O valor mais recente fica num ref para o ouvinte de scroll o ler sem ter
  // de ser registado outra vez sempre que o estado do áudio muda.
  const audioActiveRef = useRef(audioActive);
  audioActiveRef.current = audioActive;

  // Quando um capítulo acaba de carregar: saltar para a frase guardada, ou
  // voltar ao topo se for outro capítulo.
  useEffect(() => {
    if (!chapter) {
      return;
    }
    if (resumeSentenceId !== null && !jumped.current) {
      jumped.current = true;
      lastSaved.current = resumeSentenceId;
      article.current
        ?.querySelector(`[data-sentence-id="${resumeSentenceId}"]`)
        ?.scrollIntoView?.({ block: "start" });
    } else if (resumeSentenceId === null) {
      window.scrollTo(0, 0);
    }
  }, [chapter, resumeSentenceId]);

  // Sem áudio a tocar, a posição é a primeira frase visível, guardada pouco
  // depois de o leitor parar de fazer scroll e também ao abrir um capítulo.
  useEffect(() => {
    if (!chapter) {
      return;
    }
    let timer: number | undefined;
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        // Com áudio a tocar, quem manda na posição é a frase que está a ser dita.
        if (audioActiveRef.current || !article.current) {
          return;
        }
        const sentenceId = firstVisibleSentenceId(article.current);
        if (sentenceId !== null) {
          saveSentence(sentenceId);
        }
      }, SAVE_DELAY_MS);
    };
    schedule();
    // passive: true promete ao browser que não vamos cancelar o scroll, o
    // que lhe permite manter o movimento fluido.
    window.addEventListener("scroll", schedule, { passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("scroll", schedule);
    };
  }, [chapter, saveSentence]);

  // Com áudio, a posição é a frase que está a ser dita, e a página acompanha-a.
  const spokenSentenceId = player.currentSentenceId;
  useEffect(() => {
    if (spokenSentenceId === null) {
      return;
    }
    saveSentence(spokenSentenceId);
    const element = article.current?.querySelector(`[data-sentence-id="${spokenSentenceId}"]`);
    if (!element) {
      return;
    }
    // Só mexemos na página se a frase estiver a sair da zona confortável do
    // ecrã; mexer a cada frase seria enjoativo.
    const { top, bottom } = element.getBoundingClientRect();
    const comfortable = top >= HEADER_OFFSET_PX + 8 && bottom <= window.innerHeight * 0.7;
    if (!comfortable) {
      element.scrollIntoView?.({
        block: "center",
        behavior: prefersReducedMotion() ? "auto" : "smooth",
      });
    }
  }, [spokenSentenceId, saveSentence]);

  if (documentQuery.isError) {
    return (
      <main className="mx-auto max-w-2xl px-5 pt-16">
        <p role="alert" className="text-danger">
          {errorMessage(documentQuery.error)}
        </p>
        <Link to="/" className="mt-4 inline-block text-pen underline underline-offset-4">
          Voltar à biblioteca
        </Link>
      </main>
    );
  }

  const chapters = document?.chapters ?? [];
  const previous = chapters.find((item) => item.position === chapterPosition - 1);
  const next = chapters.find((item) => item.position === chapterPosition + 1);

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-rule bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3 text-sm">
          <Link to="/" className="text-pen underline underline-offset-4">
            Biblioteca
          </Link>
          <p className="min-w-0 flex-1 truncate font-book text-base font-semibold">
            {document?.title}
          </p>

          {chapters.length > 0 && (
            <label className="flex items-center gap-2">
              <span className="text-pencil">Capítulo</span>
              <ChapterSelect chapters={chapters} current={chapterPosition} />
            </label>
          )}

          <div className="flex items-center gap-1" role="group" aria-label="Tamanho da letra">
            <button
              type="button"
              className="rounded border border-rule bg-sheet px-2.5 py-1 disabled:opacity-40"
              aria-label="Diminuir a letra"
              disabled={preferences.fontSize <= FONT_SIZE_MIN}
              onClick={() => changeFontSize(-FONT_SIZE_STEP)}
            >
              A−
            </button>
            <button
              type="button"
              className="rounded border border-rule bg-sheet px-2.5 py-1 text-base disabled:opacity-40"
              aria-label="Aumentar a letra"
              disabled={preferences.fontSize >= FONT_SIZE_MAX}
              onClick={() => changeFontSize(FONT_SIZE_STEP)}
            >
              A+
            </button>
          </div>
        </div>
      </header>

      <main className="px-5 pt-10 pb-16">
        {/* A largura está em "em", por isso acompanha o tamanho da letra e a
            linha fica sempre com cerca de 65 caracteres, o que se lê bem. */}
        <article
          ref={article}
          lang={document?.language ?? undefined}
          className="mx-auto max-w-[33em] font-book leading-[1.7]"
          style={{ fontSize: `${preferences.fontSize}px` }}
        >
          {(documentQuery.isPending || chapterQuery.isPending) && (
            <p className="font-ui text-base text-pencil">A abrir o livro…</p>
          )}

          {chapterQuery.isError && (
            <p role="alert" className="font-ui text-base text-danger">
              {errorMessage(chapterQuery.error)}
            </p>
          )}

          {chapter && (
            <ChapterText
              chapter={chapter}
              // Depois de o áudio começar, a marca de "paraste aqui" já
              // cumpriu o seu papel e dá lugar ao destaque da leitura.
              markedSentenceId={spokenSentenceId === null ? resumeSentenceId : null}
              activeSentenceId={spokenSentenceId}
              onSentenceClick={player.playFromSentence}
            />
          )}
        </article>

        {chapter && (
          <nav
            aria-label="Capítulos"
            className="mx-auto mt-14 flex max-w-2xl justify-between gap-6 border-t border-rule pt-5 text-sm"
          >
            {previous ? (
              <Link to={`?c=${previous.position}`} className="text-pen underline underline-offset-4">
                Capítulo anterior
              </Link>
            ) : (
              <span />
            )}
            {next ? (
              <Link to={`?c=${next.position}`} className="text-pen underline underline-offset-4">
                Capítulo seguinte
              </Link>
            ) : (
              <span className="text-pencil">Fim do livro</span>
            )}
          </nav>
        )}
      </main>

      {chapter && (
        <PlayerBar player={player} documentId={documentId} chapterPosition={chapterPosition} />
      )}
    </>
  );
}

function ChapterSelect({ chapters, current }: { chapters: ChapterSummary[]; current: number }) {
  const [, setSearchParams] = useSearchParams();
  return (
    <select
      className="max-w-56 truncate rounded border border-rule bg-sheet px-2 py-1"
      value={current}
      onChange={(event) => setSearchParams({ c: event.target.value })}
    >
      {chapters.map((chapter) => (
        <option key={chapter.position} value={chapter.position}>
          {chapterLabel(chapter)}
        </option>
      ))}
    </select>
  );
}
