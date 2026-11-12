import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { estimateAudio, type AudioEstimate } from "../api/audio";
import { formatCount, formatUsd } from "../lib/format";
import { errorMessage } from "../lib/messages";
import { PLAYBACK_RATES, usePreferences } from "../lib/preferences";
import type { AudioPlayer } from "./useAudioPlayer";

interface PlayerBarProps {
  player: AudioPlayer;
  documentId: number;
  chapterPosition: number;
}

const BUTTON = "rounded border border-rule bg-sheet px-3 py-1.5 disabled:opacity-40";

/** Barra no fundo do leitor, com os comandos do áudio. */
export function PlayerBar({ player, documentId, chapterPosition }: PlayerBarProps) {
  const { preferences, setPlaybackRate } = usePreferences();
  const [showEstimate, setShowEstimate] = useState(false);
  const loading = player.status === "loading";
  const playing = player.status === "playing";

  return (
    // "sticky bottom-0": a barra fica colada ao fundo da janela enquanto se lê
    // e, ao chegar ao fim da página, assenta por cima do rodapé sem o tapar.
    <div className="sticky bottom-0 z-20 border-t border-rule bg-paper/95 backdrop-blur">
      {/* O elemento que toca o som. Não tem comandos próprios visíveis: os
          botões desta barra é que o controlam. */}
      <audio ref={player.audioRef} preload="auto" {...player.audioEvents} />

      {player.privatePrompt && (
        <PrivateConfirmation
          characters={player.privatePrompt.characters}
          onConfirm={player.confirmPrivate}
          onCancel={player.dismissPrivatePrompt}
        />
      )}

      {showEstimate && <EstimatePanel documentId={documentId} chapterPosition={chapterPosition} />}

      {player.error !== null && (
        <p role="alert" className="mx-auto max-w-5xl px-5 pt-3 text-sm text-danger">
          {errorMessage(player.error)}
        </p>
      )}

      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3 text-sm">
        <div className="flex items-center gap-1.5" role="group" aria-label="Áudio">
          <button type="button" className={BUTTON} onClick={player.previousSentence}>
            Frase anterior
          </button>
          <button
            type="button"
            className="min-w-24 rounded bg-pen px-4 py-1.5 font-medium text-paper disabled:opacity-60"
            disabled={loading}
            onClick={player.toggle}
          >
            {loading ? "A preparar…" : playing ? "Pausar" : "Ouvir"}
          </button>
          <button type="button" className={BUTTON} onClick={player.repeatSentence}>
            Repetir frase
          </button>
          <button type="button" className={BUTTON} onClick={player.nextSentence}>
            Frase seguinte
          </button>
        </div>

        <label className="flex items-center gap-2">
          <span className="text-pencil">Velocidade</span>
          <select
            className="rounded border border-rule bg-sheet px-2 py-1"
            value={preferences.playbackRate}
            onChange={(event) => setPlaybackRate(Number(event.target.value))}
          >
            {PLAYBACK_RATES.map((rate) => (
              <option key={rate} value={rate}>
                {rate.toLocaleString("pt-PT")}x
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className="text-pen underline underline-offset-4"
          aria-expanded={showEstimate}
          onClick={() => setShowEstimate((open) => !open)}
        >
          {showEstimate ? "Esconder o custo" : "Ver o custo do áudio"}
        </button>

        {/* Para não se confundir um bip de teste com um problema de som. */}
        {player.voice?.startsWith("fake-") && (
          <p className="text-pencil">Voz simulada: ouve-se um bip por palavra.</p>
        )}
      </div>
    </div>
  );
}

function PrivateConfirmation({
  characters,
  onConfirm,
  onCancel,
}: {
  characters: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    // role="alertdialog" diz aos leitores de ecrã que é uma pergunta que
    // precisa de resposta antes de continuar.
    <div
      role="alertdialog"
      aria-labelledby="private-title"
      aria-describedby="private-text"
      className="mx-auto max-w-5xl px-5 pt-4"
    >
      <div className="border-l-4 border-pen bg-sheet px-4 py-3 text-sm">
        <h2 id="private-title" className="font-semibold">
          Este documento está marcado como privado
        </h2>
        <p id="private-text" className="mt-1 text-pencil">
          Para gerar o áudio, o texto deste excerto ({formatCount(characters)} caracteres) é enviado
          ao serviço de voz. A confirmação vale para este documento até fechares o separador.
        </p>
        <div className="mt-3 flex gap-3">
          <button
            type="button"
            className="rounded bg-pen px-3 py-1.5 font-medium text-paper"
            onClick={onConfirm}
          >
            Enviar e ouvir
          </button>
          <button type="button" className={BUTTON} onClick={onCancel}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}

function EstimatePanel({
  documentId,
  chapterPosition,
}: {
  documentId: number;
  chapterPosition: number;
}) {
  // Duas estimativas: este capítulo e o livro inteiro. Só são pedidas quando
  // o painel abre, porque este componente só existe nessa altura.
  const chapter = useQuery({
    queryKey: ["estimate", documentId, chapterPosition],
    queryFn: () => estimateAudio(documentId, chapterPosition),
  });
  const book = useQuery({
    queryKey: ["estimate", documentId, "book"],
    queryFn: () => estimateAudio(documentId),
  });
  const failure = chapter.error ?? book.error;

  return (
    <section aria-label="Custo do áudio" className="mx-auto max-w-5xl px-5 pt-4 text-sm">
      <div className="border-l-4 border-rule bg-sheet px-4 py-3">
        {failure ? (
          <p role="alert" className="text-danger">
            {errorMessage(failure)}
          </p>
        ) : (
          <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
            <dt className="font-medium">Este capítulo</dt>
            <dd>{chapter.data ? <EstimateLine estimate={chapter.data} /> : "A calcular…"}</dd>
            <dt className="font-medium">O livro inteiro</dt>
            <dd>{book.data ? <EstimateLine estimate={book.data} /> : "A calcular…"}</dd>
          </dl>
        )}
        <p className="mt-2 text-pencil">
          Só pagas o que ainda não foi gerado, e só quando o ouves. Os valores são estimativas.
        </p>
      </div>
    </section>
  );
}

function EstimateLine({ estimate }: { estimate: AudioEstimate }) {
  if (estimate.characters_to_synthesize === 0) {
    return <>Já está todo gerado: ouvir não custa nada.</>;
  }
  return (
    <>
      {formatCount(estimate.characters_to_synthesize)} caracteres por gerar, cerca de{" "}
      {formatUsd(estimate.estimated_cost_usd)}
      {estimate.characters_cached > 0 &&
        ` (${formatCount(estimate.characters_cached)} já em cache)`}
      .
      {estimate.exceeds_monthly_limit && (
        <strong className="ml-1 font-medium text-danger">Passa o teto mensal.</strong>
      )}
    </>
  );
}
