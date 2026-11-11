import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { Link } from "react-router";

import {
  deleteDocument,
  listDocuments,
  updateDocument,
  uploadDocument,
  type DocumentSummary,
} from "../api/documents";
import { errorMessage, LANGUAGE_NAMES } from "../lib/messages";

// Chave pela qual o TanStack Query guarda a lista de documentos. Invalidá-la
// faz a lista ser pedida outra vez ao backend.
const LIBRARY_KEY = ["documents"];

export function LibraryPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  // useInfiniteQuery junta as várias páginas da lista. getNextPageParam diz
  // qual é o cursor da página seguinte (undefined quando não há mais).
  const library = useInfiniteQuery({
    queryKey: LIBRARY_KEY,
    queryFn: ({ pageParam }) => listDocuments(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  // Uma "mutation" é um pedido que altera dados. Guarda sozinha se está em
  // curso, se falhou e qual foi o resultado.
  const upload = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LIBRARY_KEY }),
  });

  const documents = library.data?.pages.flatMap((page) => page.items) ?? [];

  function importFile(file: File | undefined) {
    if (file) {
      upload.mutate(file);
    }
  }

  function handleDrop(event: DragEvent) {
    // Sem preventDefault o browser abriria o ficheiro largado em vez de o
    // entregar à página.
    event.preventDefault();
    setDragging(false);
    importFile(event.dataTransfer.files[0]);
  }

  return (
    <main
      className="mx-auto min-h-[80vh] w-full max-w-3xl px-5 pt-14 pb-10"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <header className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-book text-5xl leading-none font-semibold tracking-tight">Biblioteca</h1>
        <div className="text-right">
          <button
            type="button"
            className="rounded-md bg-pen px-4 py-2 font-medium text-paper disabled:opacity-60"
            disabled={upload.isPending}
            onClick={() => fileInput.current?.click()}
          >
            {upload.isPending ? "A importar…" : "Importar EPUB"}
          </button>
          {/* O campo de ficheiro verdadeiro fica escondido; o botão acima
              abre-o. Assim o botão tem o aspeto que quisermos. */}
          <input
            ref={fileInput}
            type="file"
            accept=".epub,application/epub+zip"
            className="sr-only"
            aria-label="Ficheiro EPUB a importar"
            onChange={(event) => {
              importFile(event.target.files?.[0]);
              // Limpar o campo permite escolher o mesmo ficheiro outra vez.
              event.target.value = "";
            }}
          />
          <p className="mt-2 text-sm text-pencil">ou arrasta um ficheiro .epub para esta página</p>
        </div>
      </header>

      {/* role="alert" e role="status" fazem os leitores de ecrã anunciar a
          mensagem quando ela aparece. */}
      {upload.isError && (
        <p role="alert" className="mt-6 border-l-4 border-danger py-1 pl-3 text-danger">
          {errorMessage(upload.error)}
        </p>
      )}
      {upload.isSuccess && (
        <p role="status" className="mt-6 border-l-4 border-ok py-1 pl-3">
          {upload.data.created
            ? `«${upload.data.document.title}» foi importado.`
            : `«${upload.data.document.title}» já estava na biblioteca.`}
        </p>
      )}

      <section
        aria-label="Livros"
        className={`mt-10 border-t-2 ${dragging ? "border-pen" : "border-ink"}`}
      >
        {dragging && <p className="py-10 text-center text-pen">Larga o ficheiro para o importar.</p>}

        {library.isPending && <p className="py-10 text-pencil">A carregar a biblioteca…</p>}

        {library.isError && (
          <p role="alert" className="py-10 text-danger">
            {errorMessage(library.error)}
          </p>
        )}

        {library.isSuccess && documents.length === 0 && !dragging && (
          <p className="py-10 font-book text-xl text-pencil">
            Ainda não tens livros. Importa um EPUB para começar a ler.
          </p>
        )}

        <ul>
          {documents.map((document) => (
            <DocumentRow key={document.id} document={document} />
          ))}
        </ul>

        {library.hasNextPage && (
          <button
            type="button"
            className="mt-6 text-pen underline underline-offset-4"
            disabled={library.isFetchingNextPage}
            onClick={() => library.fetchNextPage()}
          >
            {library.isFetchingNextPage ? "A carregar…" : "Carregar mais livros"}
          </button>
        )}
      </section>
    </main>
  );
}

function DocumentRow({ document }: { document: DocumentSummary }) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const refreshLibrary = () => queryClient.invalidateQueries({ queryKey: LIBRARY_KEY });

  const update = useMutation({
    mutationFn: (changes: { language?: string; is_private?: boolean }) =>
      updateDocument(document.id, changes),
    onSuccess: refreshLibrary,
  });
  const remove = useMutation({
    mutationFn: () => deleteDocument(document.id),
    onSuccess: refreshLibrary,
  });

  const failure = update.error ?? remove.error;

  return (
    <li className="border-b border-rule py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <Link
            to={`/documents/${document.id}`}
            className="font-book text-2xl leading-snug font-semibold text-ink underline-offset-4 hover:text-pen hover:underline"
          >
            {document.title}
          </Link>
          <p className="mt-1 text-pencil">{document.author ?? "Autor desconhecido"}</p>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-pencil">Língua</span>
            <select
              className="rounded border border-rule bg-sheet px-2 py-1"
              value={document.language ?? ""}
              disabled={update.isPending}
              onChange={(event) => update.mutate({ language: event.target.value })}
            >
              {/* Só aparece quando a língua não foi detetada; não se pode
                  voltar a escolher. */}
              {document.language === null && (
                <option value="" disabled>
                  Por escolher
                </option>
              )}
              {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="size-4 accent-(--pen)"
              checked={document.is_private}
              disabled={update.isPending}
              onChange={(event) => update.mutate({ is_private: event.target.checked })}
            />
            Privado
          </label>

          {confirmingDelete ? (
            <span className="flex items-center gap-3">
              <button
                type="button"
                className="font-medium text-danger underline underline-offset-4"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                Apagar de vez
              </button>
              <button
                type="button"
                className="text-pencil underline underline-offset-4"
                onClick={() => setConfirmingDelete(false)}
              >
                Cancelar
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="text-pencil underline underline-offset-4 hover:text-danger"
              aria-label={`Apagar «${document.title}»`}
              onClick={() => setConfirmingDelete(true)}
            >
              Apagar
            </button>
          )}
        </div>
      </div>

      {failure && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {errorMessage(failure)}
        </p>
      )}
    </li>
  );
}
