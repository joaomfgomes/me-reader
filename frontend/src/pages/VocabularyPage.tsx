import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { deleteVocabularyEntry, listVocabulary, type VocabularyEntry } from "../api/tutor";
import { errorMessage, LANGUAGE_NAMES } from "../lib/messages";

export function VocabularyPage() {
  // "" quer dizer todas as línguas.
  const [language, setLanguage] = useState("");

  // A língua faz parte da chave: mudar o filtro pede outra lista, e cada
  // filtro fica guardado em separado.
  const vocabulary = useInfiniteQuery({
    queryKey: ["vocabulary", language],
    queryFn: ({ pageParam }) =>
      listVocabulary({ cursor: pageParam, language: language || undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const entries = vocabulary.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <main className="mx-auto min-h-[80vh] w-full max-w-3xl px-5 pt-14 pb-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-book text-5xl leading-none font-semibold tracking-tight">
          Vocabulário
        </h1>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-pencil">Língua</span>
          <select
            className="rounded border border-rule bg-sheet px-2 py-1"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
          >
            <option value="">Todas</option>
            {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section aria-label="Palavras consultadas" className="mt-10 border-t-2 border-ink">
        {vocabulary.isPending && <p className="py-10 text-pencil">A carregar o vocabulário…</p>}

        {vocabulary.isError && (
          <p role="alert" className="py-10 text-danger">
            {errorMessage(vocabulary.error)}
          </p>
        )}

        {vocabulary.isSuccess && entries.length === 0 && (
          <p className="py-10 font-book text-xl text-pencil">
            {language
              ? "Ainda não consultaste nenhuma palavra nesta língua."
              : "Ainda não consultaste nenhuma palavra. Abre um livro e carrega numa palavra que não percebas."}
          </p>
        )}

        <ul>
          {entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} />
          ))}
        </ul>

        {vocabulary.hasNextPage && (
          <button
            type="button"
            className="mt-6 text-pen underline underline-offset-4"
            disabled={vocabulary.isFetchingNextPage}
            onClick={() => vocabulary.fetchNextPage()}
          >
            {vocabulary.isFetchingNextPage ? "A carregar…" : "Carregar mais palavras"}
          </button>
        )}
      </section>
    </main>
  );
}

function EntryRow({ entry }: { entry: VocabularyEntry }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => deleteVocabularyEntry(entry.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vocabulary"] }),
  });
  const { explanation } = entry;

  return (
    <li className="border-b border-rule py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="font-book text-2xl font-semibold">
          {explanation.lemma}
          {/* Se a forma encontrada no texto for diferente do lema, mostra-a também. */}
          {entry.word.toLowerCase() !== explanation.lemma.toLowerCase() && (
            <span className="ml-2 text-base font-normal text-pencil">no texto: {entry.word}</span>
          )}
        </h2>
        <p className="text-sm text-pencil">
          {LANGUAGE_NAMES[entry.language] ?? entry.language}
          {entry.lookup_count > 1 && `, consultada ${entry.lookup_count} vezes`}
        </p>
      </div>

      <p className="mt-1 font-book text-lg">{explanation.translation}</p>
      <p className="mt-1 text-sm text-pencil">
        {explanation.part_of_speech}. Pronúncia: {explanation.pronunciation} {explanation.ipa}
      </p>
      <p className="mt-2 text-sm leading-relaxed">{explanation.definition}</p>

      {/* A frase original, na língua do livro. */}
      <blockquote
        lang={entry.language}
        className="mt-3 border-l-2 border-rule pl-3 font-book italic"
      >
        {entry.sentence_text}
      </blockquote>

      <div className="mt-3 flex gap-5 text-sm">
        {entry.document_id !== null && (
          <Link
            to={`/documents/${entry.document_id}`}
            className="text-pen underline underline-offset-4"
          >
            Abrir o livro
          </Link>
        )}
        <button
          type="button"
          className="text-pencil underline underline-offset-4 hover:text-danger"
          aria-label={`Remover «${explanation.lemma}» do vocabulário`}
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          Remover
        </button>
      </div>

      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {errorMessage(remove.error)}
        </p>
      )}
    </li>
  );
}
