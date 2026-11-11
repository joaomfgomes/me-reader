import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { DocumentSummary } from "../api/documents";
import { mockApi, renderPage } from "../test/helpers";
import { LibraryPage } from "./LibraryPage";

const ALICE: DocumentSummary = {
  id: 1,
  title: "Alice's Adventures in Wonderland",
  author: "Lewis Carroll",
  language: "en",
  format: "epub",
  is_private: false,
  file_size: 136756,
  created_at: "2026-11-11T16:00:00Z",
  status: "ready",
};

const EMPTY = { items: [], next_cursor: null };
const WITH_ALICE = { items: [ALICE], next_cursor: null };

function epubFile(): File {
  return new File(["conteudo"], "livro.epub", { type: "application/epub+zip" });
}

test("biblioteca vazia convida a importar um livro", async () => {
  mockApi({ "GET /documents": { body: EMPTY } });

  renderPage(<LibraryPage />);

  expect(await screen.findByText(/Ainda não tens livros/)).toBeInTheDocument();
});

test("mostra os livros com ligação para o leitor", async () => {
  mockApi({ "GET /documents": { body: WITH_ALICE } });

  renderPage(<LibraryPage />);

  const link = await screen.findByRole("link", { name: ALICE.title });
  expect(link).toHaveAttribute("href", "/documents/1");
  expect(screen.getByText("Lewis Carroll")).toBeInTheDocument();
  expect(screen.getByLabelText("Língua")).toHaveValue("en");
  expect(screen.getByLabelText("Privado")).not.toBeChecked();
});

test("avisa quando não consegue carregar a biblioteca", async () => {
  mockApi({ "GET /documents": { status: 500, body: {} } });

  renderPage(<LibraryPage />);

  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

test("importar um livro mostra a confirmação e atualiza a lista", async () => {
  const calls = mockApi({
    "GET /documents": { body: WITH_ALICE },
    "POST /documents": { status: 201, body: ALICE },
  });
  renderPage(<LibraryPage />);
  await screen.findByRole("link", { name: ALICE.title });

  await userEvent.upload(screen.getByLabelText("Ficheiro EPUB a importar"), epubFile());

  expect(await screen.findByRole("status")).toHaveTextContent("foi importado");
  // O ficheiro seguiu num formulário, no campo "file".
  const upload = calls.find((call) => call.method === "POST");
  expect((upload?.body as FormData).get("file")).toBeInstanceOf(File);
  // A lista foi pedida outra vez depois da importação.
  await waitFor(() => expect(calls.filter((call) => call.method === "GET").length).toBe(2));
});

test("importar um livro repetido diz que já lá estava", async () => {
  mockApi({
    "GET /documents": { body: WITH_ALICE },
    "POST /documents": { status: 200, body: ALICE },
  });
  renderPage(<LibraryPage />);

  await userEvent.upload(screen.getByLabelText("Ficheiro EPUB a importar"), epubFile());

  expect(await screen.findByRole("status")).toHaveTextContent("já estava na biblioteca");
});

test("explica o erro quando o ficheiro não é um EPUB", async () => {
  mockApi({
    "GET /documents": { body: EMPTY },
    "POST /documents": {
      status: 415,
      body: { code: "unsupported_file_type", title: "Tipo de ficheiro não suportado" },
    },
  });
  renderPage(<LibraryPage />);

  await userEvent.upload(screen.getByLabelText("Ficheiro EPUB a importar"), epubFile());

  expect(await screen.findByRole("alert")).toHaveTextContent("O ficheiro não é um EPUB");
});

test("corrigir a língua envia só esse campo", async () => {
  const calls = mockApi({
    "GET /documents": { body: WITH_ALICE },
    "PATCH /documents/1": { body: { ...ALICE, language: "fr" } },
  });
  renderPage(<LibraryPage />);

  await userEvent.selectOptions(await screen.findByLabelText("Língua"), "Francês");

  await waitFor(() =>
    expect(calls).toContainEqual({
      method: "PATCH",
      path: "/documents/1",
      body: { language: "fr" },
    }),
  );
});

test("apagar pede confirmação antes de enviar o pedido", async () => {
  const calls = mockApi({
    "GET /documents": { body: WITH_ALICE },
    "DELETE /documents/1": { status: 204 },
  });
  renderPage(<LibraryPage />);

  await userEvent.click(await screen.findByRole("button", { name: `Apagar «${ALICE.title}»` }));
  // O primeiro clique só mostra a confirmação.
  expect(calls.some((call) => call.method === "DELETE")).toBe(false);

  await userEvent.click(screen.getByRole("button", { name: "Apagar de vez" }));

  await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
});

test("cancelar a confirmação não apaga nada", async () => {
  const calls = mockApi({ "GET /documents": { body: WITH_ALICE } });
  renderPage(<LibraryPage />);

  await userEvent.click(await screen.findByRole("button", { name: `Apagar «${ALICE.title}»` }));
  await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

  expect(screen.queryByRole("button", { name: "Apagar de vez" })).not.toBeInTheDocument();
  expect(calls.some((call) => call.method === "DELETE")).toBe(false);
});
