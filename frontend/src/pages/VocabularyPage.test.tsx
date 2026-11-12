import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { VocabularyEntry } from "../api/tutor";
import { mockApi, renderPage } from "../test/helpers";
import { VocabularyPage } from "./VocabularyPage";

const SAT: VocabularyEntry = {
  id: 1,
  language: "en",
  word: "sat",
  explanation: {
    lemma: "sit",
    part_of_speech: "verbo irregular, passado simples",
    translation: "sentou-se",
    definition: "Passado de «sit» (sentar-se).",
    pronunciation: "SÉT",
    ipa: "/sæt/",
  },
  sentence_text: "The cat sat on the mat.",
  document_id: 4,
  lookup_count: 3,
  created_at: "2026-11-12T10:00:00Z",
  updated_at: "2026-11-12T11:00:00Z",
};

const QUAI: VocabularyEntry = {
  ...SAT,
  id: 2,
  language: "fr",
  word: "quai",
  explanation: { ...SAT.explanation, lemma: "quai", translation: "cais" },
  sentence_text: "Il s'était trompé de quai.",
  document_id: null,
  lookup_count: 1,
};

const EMPTY = { items: [], next_cursor: null };

test("vocabulário vazio explica como juntar palavras", async () => {
  mockApi({ "GET /vocabulary": { body: EMPTY } });

  renderPage(<VocabularyPage />);

  expect(await screen.findByText(/Ainda não consultaste nenhuma palavra/)).toBeInTheDocument();
});

test("mostra cada palavra com a explicação e a frase original", async () => {
  mockApi({ "GET /vocabulary": { body: { items: [QUAI, SAT], next_cursor: null } } });

  renderPage(<VocabularyPage />);

  const sat = (await screen.findByRole("heading", { name: /sit/ })).closest("li");
  if (!sat) {
    throw new Error("entrada não encontrada");
  }
  // O lema é o título; a forma do texto aparece ao lado quando é diferente.
  expect(within(sat).getByText("no texto: sat")).toBeInTheDocument();
  expect(within(sat).getByText("sentou-se")).toBeInTheDocument();
  expect(within(sat).getByText("The cat sat on the mat.")).toHaveAttribute("lang", "en");
  expect(within(sat).getByText(/consultada 3 vezes/)).toBeInTheDocument();
  expect(within(sat).getByRole("link", { name: "Abrir o livro" })).toHaveAttribute(
    "href",
    "/documents/4",
  );

  // Uma palavra de um livro já apagado continua lá, sem ligação para o livro.
  const quai = screen.getByRole("heading", { name: "quai" }).closest("li");
  expect(within(quai as HTMLElement).queryByRole("link")).not.toBeInTheDocument();
  expect(within(quai as HTMLElement).getByText("Francês")).toBeInTheDocument();
});

test("o filtro pede só as palavras da língua escolhida", async () => {
  const calls = mockApi({
    "GET /vocabulary": { body: { items: [QUAI, SAT], next_cursor: null } },
    "GET /vocabulary?language=fr": { body: { items: [QUAI], next_cursor: null } },
  });
  renderPage(<VocabularyPage />);
  await screen.findByRole("heading", { name: /sit/ });

  await userEvent.selectOptions(screen.getByLabelText("Língua"), "Francês");

  await waitFor(() => expect(screen.queryByRole("heading", { name: /sit/ })).not.toBeInTheDocument());
  expect(screen.getByRole("heading", { name: "quai" })).toBeInTheDocument();
  expect(calls.map((call) => call.path)).toContain("/vocabulary?language=fr");
});

test("remover uma palavra envia o pedido e atualiza a lista", async () => {
  let deleted = false;
  const calls = mockApi({
    "GET /vocabulary": () => ({ body: deleted ? EMPTY : { items: [SAT], next_cursor: null } }),
    "DELETE /vocabulary/1": () => {
      deleted = true;
      return { status: 204 };
    },
  });
  renderPage(<VocabularyPage />);

  await userEvent.click(
    await screen.findByRole("button", { name: "Remover «sit» do vocabulário" }),
  );

  expect(await screen.findByText(/Ainda não consultaste nenhuma palavra/)).toBeInTheDocument();
  expect(calls.some((call) => call.method === "DELETE")).toBe(true);
});

test("carrega mais palavras quando há outra página", async () => {
  mockApi({
    "GET /vocabulary": { body: { items: [SAT], next_cursor: "abc" } },
    "GET /vocabulary?cursor=abc": { body: { items: [QUAI], next_cursor: null } },
  });
  renderPage(<VocabularyPage />);

  await userEvent.click(await screen.findByRole("button", { name: "Carregar mais palavras" }));

  expect(await screen.findByRole("heading", { name: "quai" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Carregar mais palavras" })).not.toBeInTheDocument();
});
