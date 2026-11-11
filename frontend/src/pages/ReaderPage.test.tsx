import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { ChapterDetail, DocumentDetail } from "../api/documents";
import { mockApi, renderPage } from "../test/helpers";
import { ReaderPage, SAVE_DELAY_MS } from "./ReaderPage";

const DOCUMENT: DocumentDetail = {
  id: 1,
  title: "Livro de teste",
  author: "Autora",
  language: "en",
  format: "epub",
  is_private: false,
  file_size: 1000,
  created_at: "2026-11-11T16:00:00Z",
  status: "ready",
  chapters: [
    { position: 0, title: "Chapter One" },
    { position: 1, title: null },
  ],
  reading_position: null,
};

// Um bloco com dois parágrafos: o título e duas frases.
const CHAPTER_0: ChapterDetail = {
  document_id: 1,
  position: 0,
  title: "Chapter One",
  blocks: [
    {
      id: 5,
      position: 0,
      text: "Chapter One\nThe cat sat. It was warm.",
      sentences: [
        { id: 10, position: 0, text: "Chapter One", start_offset: 0, end_offset: 11, words: [] },
        { id: 11, position: 1, text: "The cat sat.", start_offset: 12, end_offset: 24, words: [] },
        { id: 12, position: 2, text: "It was warm.", start_offset: 25, end_offset: 37, words: [] },
      ],
    },
  ],
};

const CHAPTER_1: ChapterDetail = {
  document_id: 1,
  position: 1,
  title: null,
  blocks: [
    {
      id: 6,
      position: 0,
      text: "The dog slept. Then it rained.",
      sentences: [
        { id: 20, position: 0, text: "The dog slept.", start_offset: 0, end_offset: 14, words: [] },
        { id: 21, position: 1, text: "Then it rained.", start_offset: 15, end_offset: 30, words: [] },
      ],
    },
  ],
};

const POSITION = { sentence_id: 10, block_id: 5, chapter_position: 0, updated_at: "x" };

function routes(document: DocumentDetail = DOCUMENT) {
  return {
    "GET /documents/1": { body: document },
    "GET /documents/1/chapters/0": { body: CHAPTER_0 },
    "GET /documents/1/chapters/1": { body: CHAPTER_1 },
    "PUT /documents/1/position": { body: POSITION },
  };
}

function renderReader(url = "/documents/1") {
  return renderPage(<ReaderPage />, { path: "/documents/:id", url });
}

test("mostra o primeiro capítulo com o título e os parágrafos", async () => {
  mockApi(routes());

  renderReader();

  // O título aparece uma só vez, como cabeçalho.
  expect(await screen.findByRole("heading", { name: "Chapter One" })).toBeInTheDocument();
  // As duas frases estão no mesmo parágrafo, cada uma no seu elemento.
  const first = screen.getByText("The cat sat.");
  const second = screen.getByText("It was warm.");
  expect(first.closest("p")).toBe(second.closest("p"));
  expect(first).toHaveAttribute("data-sentence-id", "11");
  expect(first.closest("article")).toHaveAttribute("lang", "en");
});

test("guarda a posição pouco depois de abrir o capítulo", async () => {
  const calls = mockApi(routes());

  renderReader();
  await screen.findByText("The cat sat.");

  await waitFor(
    () =>
      expect(calls).toContainEqual({
        method: "PUT",
        path: "/documents/1/position",
        body: { sentence_id: 10 },
      }),
    { timeout: SAVE_DELAY_MS + 1500 },
  );
});

test("abre no capítulo onde o leitor parou e marca a frase", async () => {
  const saved = { sentence_id: 21, block_id: 6, chapter_position: 1, updated_at: "x" };
  const calls = mockApi(routes({ ...DOCUMENT, reading_position: saved }));

  renderReader();

  const sentence = await screen.findByText("Then it rained.");
  expect(sentence).toHaveClass("marked");
  expect(screen.getByText("The dog slept.")).not.toHaveClass("marked");
  expect(calls.some((call) => call.path === "/documents/1/chapters/0")).toBe(false);
  expect(screen.getByLabelText("Capítulo")).toHaveValue("1");
});

test("o capítulo do endereço tem prioridade sobre a posição guardada", async () => {
  const saved = { sentence_id: 21, block_id: 6, chapter_position: 1, updated_at: "x" };
  mockApi(routes({ ...DOCUMENT, reading_position: saved }));

  renderReader("/documents/1?c=0");

  expect(await screen.findByText("The cat sat.")).toBeInTheDocument();
});

test("o índice e os botões mudam de capítulo", async () => {
  mockApi(routes());
  renderReader();
  await screen.findByText("The cat sat.");

  // Capítulos sem título aparecem no índice como "Parte N".
  await userEvent.selectOptions(screen.getByLabelText("Capítulo"), "Parte 2");
  expect(await screen.findByText("The dog slept.")).toBeInTheDocument();
  expect(screen.getByText("Fim do livro")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "Capítulo anterior" }));
  expect(await screen.findByText("The cat sat.")).toBeInTheDocument();
});

test("os botões de tamanho mudam a letra do texto e a escolha fica guardada", async () => {
  mockApi(routes());
  renderReader();
  const article = (await screen.findByText("The cat sat.")).closest("article");
  expect(article).toHaveStyle({ fontSize: "20px" });

  await userEvent.click(screen.getByRole("button", { name: "Aumentar a letra" }));

  expect(article).toHaveStyle({ fontSize: "22px" });
  expect(JSON.parse(localStorage.getItem("reader.preferences") ?? "{}").fontSize).toBe(22);
});

test("livro que já não existe mostra o erro e o caminho de volta", async () => {
  mockApi({
    "GET /documents/1": {
      status: 404,
      body: { code: "document_not_found", title: "Documento não encontrado" },
    },
  });

  renderReader();

  expect(await screen.findByRole("alert")).toHaveTextContent("já não está na biblioteca");
  expect(screen.getByRole("link", { name: "Voltar à biblioteca" })).toHaveAttribute("href", "/");
});
