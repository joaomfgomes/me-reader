import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { explainWord } from "../api/tutor";
import { formatCount } from "../lib/format";
import { errorMessage } from "../lib/messages";
import type { SelectedWord } from "./ChapterText";

// Documentos privados cujo envio de texto ao tutor o utilizador já confirmou.
// É uma confirmação à parte da do áudio, porque o texto vai para outro
// serviço. Vive só em memória, até fechar ou recarregar o separador.
const confirmedPrivateDocuments = new Set<number>();

interface TutorPanelProps {
  documentId: number;
  word: SelectedWord;
  onClose: () => void;
  /** Tocar o áudio a partir da frase da palavra. */
  onPlayFromSentence: () => void;
}

/** Explicação da palavra em que o leitor carregou, como uma nota à margem. */
export function TutorPanel({ documentId, word, onClose, onPlayFromSentence }: TutorPanelProps) {
  const queryClient = useQueryClient();
  const [confirmed, setConfirmed] = useState(() => confirmedPrivateDocuments.has(documentId));

  // Usamos useQuery, e não uma "mutation", para o TanStack Query guardar a
  // explicação: voltar a carregar na mesma palavra mostra-a logo, sem novo
  // pedido. A chave inclui a confirmação, para o pedido se repetir quando o
  // utilizador confirma o envio de um documento privado.
  const explanation = useQuery({
    queryKey: ["tutor-word", word.sentenceId, word.start, word.end, confirmed],
    queryFn: () =>
      explainWord({
        sentenceId: word.sentenceId,
        wordStart: word.start,
        wordEnd: word.end,
        confirmPrivate: confirmed,
      }),
    // Uma explicação não muda: nunca é preciso pedi-la outra vez.
    staleTime: Infinity,
    retry: false,
  });

  // Cada consulta mexe no vocabulário e no consumo: as páginas que os mostram
  // têm de ir buscar os números novos.
  useEffect(() => {
    if (explanation.data) {
      void queryClient.invalidateQueries({ queryKey: ["vocabulary"] });
      void queryClient.invalidateQueries({ queryKey: ["usage"] });
    }
  }, [explanation.data, queryClient]);

  const needsConfirmation =
    explanation.error instanceof ApiError &&
    explanation.error.code === "private_document_confirmation_required";
  const data = explanation.data?.explanation;

  return (
    // Fica no canto inferior direito, por cima da barra do áudio, para não
    // tapar a linha que se está a ler. Só em ecrãs muito largos (2xl) há
    // margem suficiente ao lado do texto, e aí sobe para junto do topo.
    <aside
      aria-label={`Explicação de «${word.text}»`}
      className="fixed right-3 bottom-28 z-30 max-h-[55vh] w-80 max-w-[calc(100vw-1.5rem)] overflow-auto border-l-4 border-pen bg-sheet px-5 py-4 shadow-lg 2xl:top-24 2xl:right-6 2xl:bottom-auto"
    >
      <div className="flex items-start justify-between gap-4">
        <h2 className="font-book text-3xl leading-tight font-semibold">{word.text}</h2>
        <button
          type="button"
          className="text-sm text-pencil underline underline-offset-4"
          onClick={onClose}
        >
          Fechar
        </button>
      </div>

      {explanation.isPending && <p className="mt-3 text-sm text-pencil">A pedir a explicação…</p>}

      {needsConfirmation && (
        <div role="alertdialog" aria-labelledby="tutor-private-title" className="mt-3 text-sm">
          <h3 id="tutor-private-title" className="font-semibold">
            Este documento está marcado como privado
          </h3>
          <p className="mt-1 text-pencil">
            Para explicar a palavra, a frase e as duas frases vizinhas (
            {formatCount(Number((explanation.error as ApiError).extras.characters ?? 0))}{" "}
            caracteres) são enviadas ao serviço do tutor. A confirmação vale para este documento
            até fechares o separador.
          </p>
          <button
            type="button"
            className="mt-3 rounded bg-pen px-3 py-1.5 font-medium text-paper"
            onClick={() => {
              confirmedPrivateDocuments.add(documentId);
              setConfirmed(true);
            }}
          >
            Enviar e explicar
          </button>
        </div>
      )}

      {explanation.isError && !needsConfirmation && (
        <div className="mt-3 text-sm">
          <p role="alert" className="text-danger">
            {errorMessage(explanation.error)}
          </p>
          <button
            type="button"
            className="mt-2 text-pen underline underline-offset-4"
            onClick={() => void explanation.refetch()}
          >
            Tentar outra vez
          </button>
        </div>
      )}

      {data && (
        <>
          <p className="mt-2 font-book text-xl">{data.translation}</p>
          <p className="mt-3 text-sm leading-relaxed">{data.definition}</p>
          <dl className="mt-4 space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="text-pencil">Lema</dt>
              <dd className="font-book">{data.lemma}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-pencil">Classe</dt>
              <dd>{data.part_of_speech}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-pencil">Pronúncia</dt>
              <dd>
                {data.pronunciation} <span className="text-pencil">{data.ipa}</span>
              </dd>
            </div>
          </dl>
        </>
      )}

      <button
        type="button"
        className="mt-4 text-sm text-pen underline underline-offset-4"
        onClick={onPlayFromSentence}
      >
        Ouvir a partir desta frase
      </button>
    </aside>
  );
}
