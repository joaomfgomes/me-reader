// Leitor de áudio: pede o áudio bloco a bloco, toca-o e acende a palavra que
// está a ser dita.
//
// Um "hook" é uma função que junta estado e comportamento para um componente
// usar. Este devolve o estado do leitor e as ações (tocar, pausar, saltar).

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import { requestBlockAudio, type BlockAudio } from "../api/audio";
import { ApiError } from "../api/client";
import type { Block, ChapterDetail } from "../api/documents";
import { wordKey } from "./ChapterText";

export type PlayerStatus = "idle" | "loading" | "playing" | "paused";

/** Uma palavra com tempo: quando começa e que elemento acender. */
interface TimelineEntry {
  startMs: number;
  key: string;
  sentenceId: number;
}

export interface PrivatePrompt {
  sentenceId: number;
  /** Quantos caracteres seriam enviados ao serviço de voz. */
  characters: number;
}

// Documentos privados cujo envio de texto o utilizador já confirmou. Vive só
// em memória: ao fechar ou recarregar o separador, a confirmação volta a ser
// pedida.
const confirmedPrivateDocuments = new Set<number>();

/** Junta as palavras do bloco aos tempos devolvidos pelo backend. */
function buildTimeline(block: Block, audio: BlockAudio): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  // audio.words tem uma entrada por palavra do bloco, pela mesma ordem em que
  // as palavras aparecem nas frases. Basta percorrer as duas listas a par.
  let index = 0;
  for (const sentence of block.sentences) {
    for (const [start] of sentence.words) {
      const timed = audio.words[index];
      index += 1;
      if (timed && timed.start_ms !== null) {
        entries.push({
          startMs: timed.start_ms,
          key: wordKey(block.id, start),
          sentenceId: sentence.id,
        });
      }
    }
  }
  return entries;
}

/** Índice da última entrada que já começou no instante dado (pesquisa binária). */
function entryAt(timeline: TimelineEntry[], timeMs: number): number {
  let low = 0;
  let high = timeline.length - 1;
  let found = -1;
  // Como a lista está ordenada por tempo, cortamo-la ao meio a cada passo em
  // vez de a percorrer toda: importa porque isto corre dezenas de vezes por
  // segundo.
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (timeline[middle].startMs <= timeMs) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

interface Options {
  documentId: number;
  chapter: ChapterDetail | undefined;
  playbackRate: number;
  /** Onde procurar os elementos das palavras. */
  container: RefObject<HTMLElement | null>;
  /** A frase por onde começar quando ainda nada tocou. */
  getStartSentenceId: () => number | null;
}

export function useAudioPlayer({
  documentId,
  chapter,
  playbackRate,
  container,
  getStartSentenceId,
}: Options) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [status, setStatus] = useState<PlayerStatus>("idle");
  const [error, setError] = useState<unknown>(null);
  const [currentSentenceId, setCurrentSentenceId] = useState<number | null>(null);
  const [voice, setVoice] = useState<string | null>(null);
  const [privatePrompt, setPrivatePrompt] = useState<PrivatePrompt | null>(null);

  // Valores que mudam sem precisar de redesenhar o ecrã ficam em "refs".
  const audioByBlock = useRef(new Map<number, BlockAudio>());
  const timeline = useRef<TimelineEntry[]>([]);
  const loadedBlockId = useRef<number | null>(null);
  const litWord = useRef<Element | null>(null);
  const litSentenceId = useRef<number | null>(null);
  const frame = useRef<number | undefined>(undefined);
  // Cada pedido de áudio recebe um número. Se o utilizador mudar de ideias
  // enquanto o pedido está em curso, o número deixa de ser o mais recente e a
  // resposta, quando chegar, é ignorada.
  const latestRequest = useRef(0);

  // Todas as frases do capítulo por ordem, para "frase anterior" e "seguinte".
  const sentenceIds = useMemo(
    () => chapter?.blocks.flatMap((block) => block.sentences.map((sentence) => sentence.id)) ?? [],
    [chapter],
  );

  const clearWord = useCallback(() => {
    litWord.current?.classList.remove("word-now");
    litWord.current = null;
  }, []);

  /** Acende a palavra e a frase que correspondem ao instante atual do áudio. */
  const sync = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const entry = timeline.current[entryAt(timeline.current, audio.currentTime * 1000)];
    if (!entry) {
      return;
    }
    const element = container.current?.querySelector(`[data-word-key="${entry.key}"]`) ?? null;
    if (element !== litWord.current) {
      // A palavra é acesa diretamente no elemento, sem passar pelo React:
      // muda várias vezes por segundo e redesenhar o capítulo de cada vez
      // seria um desperdício.
      clearWord();
      element?.classList.add("word-now");
      litWord.current = element;
    }
    if (entry.sentenceId !== litSentenceId.current) {
      litSentenceId.current = entry.sentenceId;
      // A frase muda de poucos em poucos segundos, por isso pode ser estado
      // normal do React; é também o que faz guardar a posição de leitura.
      setCurrentSentenceId(entry.sentenceId);
    }
  }, [clearWord, container]);

  const stopLoop = useCallback(() => {
    if (frame.current !== undefined) {
      cancelAnimationFrame(frame.current);
      frame.current = undefined;
    }
  }, []);

  const startLoop = useCallback(() => {
    stopLoop();
    // requestAnimationFrame chama a função antes de cada redesenho do ecrã
    // (cerca de 60 vezes por segundo). O evento "timeupdate" do áudio só
    // dispara umas 4 vezes por segundo, pouco para acompanhar as palavras.
    const tick = () => {
      sync();
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }, [stopLoop, sync]);

  const playFromSentence = useCallback(
    async (sentenceId: number, confirmPrivate = false) => {
      const audio = audioRef.current;
      const blockIndex =
        chapter?.blocks.findIndex((block) =>
          block.sentences.some((sentence) => sentence.id === sentenceId),
        ) ?? -1;
      if (!audio || !chapter || blockIndex === -1) {
        return;
      }
      const block = chapter.blocks[blockIndex];
      const request = ++latestRequest.current;
      setError(null);
      setPrivatePrompt(null);

      let blockAudio = audioByBlock.current.get(block.id);
      if (!blockAudio) {
        audio.pause();
        setStatus("loading");
        try {
          blockAudio = await requestBlockAudio(
            block.id,
            confirmPrivate || confirmedPrivateDocuments.has(documentId),
          );
        } catch (failure) {
          if (request !== latestRequest.current) {
            return;
          }
          setStatus("idle");
          if (
            failure instanceof ApiError &&
            failure.code === "private_document_confirmation_required"
          ) {
            // Não é um erro: o backend está a pedir a confirmação do utilizador.
            const characters = Number(failure.extras.characters ?? block.text.length);
            setPrivatePrompt({ sentenceId, characters });
          } else {
            setError(failure);
          }
          return;
        }
        if (request !== latestRequest.current) {
          return;
        }
        audioByBlock.current.set(block.id, blockAudio);
      }

      const entries = buildTimeline(block, blockAudio);
      // A primeira palavra com tempo desta frase ou, se a frase não tiver
      // nenhuma (só pontuação, por exemplo), da frase seguinte.
      const order = block.sentences.map((sentence) => sentence.id);
      const target = order.indexOf(sentenceId);
      const first = entries.find((entry) => order.indexOf(entry.sentenceId) >= target);
      if (!first) {
        // Não há mais nada para dizer neste bloco: passa ao seguinte.
        const nextBlock = chapter.blocks[blockIndex + 1];
        if (nextBlock?.sentences[0]) {
          void playFromSentence(nextBlock.sentences[0].id);
        } else {
          setStatus("idle");
        }
        return;
      }

      timeline.current = entries;
      setVoice(blockAudio.voice);
      if (loadedBlockId.current !== block.id) {
        loadedBlockId.current = block.id;
        audio.src = blockAudio.audio_url;
      }
      audio.currentTime = first.startMs / 1000;
      audio.playbackRate = playbackRate;
      sync();
      try {
        await audio.play();
      } catch {
        if (request === latestRequest.current) {
          setStatus("paused");
          setError(new ApiError(0, "playback_failed", "Falha ao tocar o áudio"));
        }
      }
    },
    [chapter, documentId, playbackRate, sync],
  );

  // Ao mudar de capítulo (ou ao sair do leitor), pára tudo e esquece o estado.
  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      latestRequest.current += 1;
      audio?.pause();
      stopLoop();
      clearWord();
      timeline.current = [];
      loadedBlockId.current = null;
      litSentenceId.current = null;
      setStatus("idle");
      setCurrentSentenceId(null);
      setError(null);
      setPrivatePrompt(null);
    };
  }, [chapter, stopLoop, clearWord]);

  // A velocidade é aplicada pelo browser sobre o mesmo ficheiro: mudar de
  // velocidade não gera áudio novo nem custa nada (ADR-004).
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate]);

  /** A frase a partir da qual as ações de salto se orientam. */
  const anchorSentenceId = () => currentSentenceId ?? getStartSentenceId() ?? sentenceIds[0];

  function toggle() {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    if (status === "playing") {
      audio.pause();
    } else if (status === "paused" && loadedBlockId.current !== null && !error) {
      void audio.play();
    } else {
      const start = anchorSentenceId();
      if (start !== undefined) {
        void playFromSentence(start);
      }
    }
  }

  function jump(offset: number) {
    const anchor = anchorSentenceId();
    const index = anchor === undefined ? -1 : sentenceIds.indexOf(anchor);
    const target = sentenceIds[index + offset];
    if (target !== undefined) {
      void playFromSentence(target);
    }
  }

  return {
    audioRef,
    status,
    error,
    voice,
    currentSentenceId,
    privatePrompt,
    toggle,
    playFromSentence,
    previousSentence: () => jump(-1),
    nextSentence: () => jump(1),
    repeatSentence: () => jump(0),
    confirmPrivate: () => {
      if (privatePrompt) {
        confirmedPrivateDocuments.add(documentId);
        void playFromSentence(privatePrompt.sentenceId, true);
      }
    },
    dismissPrivatePrompt: () => setPrivatePrompt(null),
    // Ligações aos eventos do elemento <audio>. É o próprio elemento que
    // manda no estado: o ecrã só diz "a tocar" quando o browser o confirma.
    audioEvents: {
      onPlay: () => {
        setStatus("playing");
        startLoop();
      },
      onPause: () => {
        stopLoop();
        setStatus((current) => (current === "playing" ? "paused" : current));
      },
      onTimeUpdate: sync,
      onEnded: () => {
        stopLoop();
        const blockIndex =
          chapter?.blocks.findIndex((block) => block.id === loadedBlockId.current) ?? -1;
        const nextBlock = chapter?.blocks[blockIndex + 1];
        if (nextBlock?.sentences[0]) {
          void playFromSentence(nextBlock.sentences[0].id);
        } else {
          // Fim do capítulo: o áudio pára aqui.
          clearWord();
          setStatus("idle");
        }
      },
      onError: () => {
        stopLoop();
        setStatus("paused");
        setError(new ApiError(0, "playback_failed", "Falha ao tocar o áudio"));
      },
    },
  };
}

export type AudioPlayer = ReturnType<typeof useAudioPlayer>;
