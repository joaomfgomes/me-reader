import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { ChapterDetail, DocumentDetail } from "../api/documents";
import type { WordResponse } from "../api/tutor";
import { mockApi, renderPage, type ApiCall } from "../test/helpers";
import { ReaderPage } from "./ReaderPage";

// Cada teste usa um documento com id diferente quando precisa de começar sem
// a confirmação de privado dada noutro teste (ela fica em memória).
function documentWith(id: number): DocumentDetail {
  return {
    id,
    title: "Livro de teste",
    author: "Autora",
    language: "en",
    format: "epub",
    is_private: false,
    file_size: 1000,
    created_at: "2026-11-11T16:00:00Z",
    status: "ready",
    chapters: [{ position: 0, title: null }],
    reading_position: null,
  };
}

function chapterOf(documentId: number): ChapterDetail {
  return {
    document_id: documentId,
    position: 0,
    title: null,
    blocks: [
      {
        id: 5,
        position: 0,
        text: "The cat sat. It was warm.",
        sentences: [
          {
            id: 11,
            position: 0,
            text: "The cat sat.",
            start_offset: 0,
            end_offset: 12,
            words: [[0, 3], [4, 7], [8, 11]],
          },
          {
            id: 12,
            position: 1,
            text: "It was warm.",
            start_offset: 13,
            end_offset: 25,
            words: [[13, 15], [16, 19], [20, 24]],
          },
        ],
      },
    ],
  };
}

const SAT: WordResponse = {
  word: "sat",
  sentence_id: 11,
  cached: false,
  vocabulary_entry_id: 1,
  explanation: {
    lemma: "sit",
    part_of_speech: "verbo irregular, passado simples",
    translation: "sentou-se",
    definition: "Passado de «sit» (sentar-se).",
    pronunciation: "SÉT",
    ipa: "/sæt/",
  },
};

async function renderReader(
  overrides: Parameters<typeof mockApi>[0] = {},
  documentId = 1,
): Promise<ApiCall[]> {
  const calls = mockApi({
    [`GET /documents/${documentId}`]: { body: documentWith(documentId) },
    [`GET /documents/${documentId}/chapters/0`]: { body: chapterOf(documentId) },
    [`PUT /documents/${documentId}/position`]: {
      body: { sentence_id: 11, block_id: 5, chapter_position: 0, updated_at: "x" },
    },
    "POST /tutor/word": { body: SAT },
    ...overrides,
  });
  renderPage(<ReaderPage />, { path: "/documents/:id", url: `/documents/${documentId}` });
  await screen.findByText("cat");
  return calls;
}

function tutorRequests(calls: ApiCall[]): ApiCall[] {
  return calls.filter((call) => call.path === "/tutor/word");
}

test("carregar numa palavra pede a explicação pela posição e mostra-a", async () => {
  const calls = await renderReader();

  await userEvent.click(screen.getByText("sat"));

  const panel = await screen.findByRole("complementary", { name: "Explicação de «sat»" });
  expect(await within(panel).findByText("sentou-se")).toBeInTheDocument();
  expect(within(panel).getByText("Passado de «sit» (sentar-se).")).toBeInTheDocument();
  expect(within(panel).getByText("sit")).toBeInTheDocument();
  expect(within(panel).getByText("verbo irregular, passado simples")).toBeInTheDocument();
  expect(within(panel).getByText("/sæt/")).toBeInTheDocument();
  // O pedido identifica a palavra pela frase e pela posição, sem enviar texto.
  expect(tutorRequests(calls)).toEqual([
    {
      method: "POST",
      path: "/tutor/word",
      body: { sentence_id: 11, word_start: 8, word_end: 11, confirm_private: false },
    },
  ]);
  // A palavra fica sublinhada no texto.
  expect(document.querySelector('[data-word-key="5-8"]')).toHaveClass("word-selected");
});

test("carregar noutra palavra troca a explicação e o sublinhado", async () => {
  const calls = await renderReader({
    "POST /tutor/word": (call) => {
      const start = (call.body as { word_start: number }).word_start;
      return start === 8
        ? { body: SAT }
        : {
            body: {
              ...SAT,
              word: "warm",
              sentence_id: 12,
              explanation: { ...SAT.explanation, lemma: "warm", translation: "quente" },
            },
          };
    },
  });
  await userEvent.click(screen.getByText("sat"));
  await screen.findByText("sentou-se");

  await userEvent.click(screen.getByText("warm"));

  expect(await screen.findByText("quente")).toBeInTheDocument();
  expect(screen.queryByText("sentou-se")).not.toBeInTheDocument();
  expect(document.querySelectorAll(".word-selected")).toHaveLength(1);
  expect(document.querySelector('[data-word-key="5-20"]')).toHaveClass("word-selected");

  // Voltar à primeira palavra mostra a explicação guardada, sem novo pedido.
  await userEvent.click(screen.getByText("sat"));
  expect(await screen.findByText("sentou-se")).toBeInTheDocument();
  expect(tutorRequests(calls)).toHaveLength(2);
});

test("fechar o painel tira o sublinhado", async () => {
  await renderReader();
  await userEvent.click(screen.getByText("sat"));
  await screen.findByText("sentou-se");

  await userEvent.click(screen.getByRole("button", { name: "Fechar" }));

  expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  expect(document.querySelector(".word-selected")).not.toBeInTheDocument();
});

test("carregar numa palavra pausa o áudio", async () => {
  await renderReader({
    "POST /blocks/5/audio": {
      body: {
        block_id: 5,
        audio_url: "/api/v1/audio/aaa",
        media_type: "audio/mpeg",
        duration_ms: 4000,
        voice: "en-US-JennyNeural",
        cached: true,
        words: [0, 4, 8, 13, 16, 20].map((start, index) => ({
          start,
          end: start + 3,
          start_ms: index * 500,
          end_ms: index * 500 + 400,
        })),
      },
    },
  });
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  await userEvent.click(screen.getByText("sat"));

  expect(await screen.findByRole("button", { name: "Ouvir" })).toBeInTheDocument();
});

test("documento privado pede confirmação antes de enviar a frase ao tutor", async () => {
  const calls = await renderReader(
    {
      "POST /tutor/word": (call) =>
        (call.body as { confirm_private: boolean }).confirm_private
          ? { body: SAT }
          : {
              status: 409,
              body: { code: "private_document_confirmation_required", characters: 120 },
            },
    },
    7,
  );

  await userEvent.click(screen.getByText("sat"));

  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("marcado como privado");
  expect(dialog).toHaveTextContent("120 caracteres");
  expect(screen.queryByText("sentou-se")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Enviar e explicar" }));

  expect(await screen.findByText("sentou-se")).toBeInTheDocument();
  expect(tutorRequests(calls).map((call) => (call.body as { confirm_private: boolean }).confirm_private)).toEqual([false, true]);
});

test("teto mensal do tutor atingido mostra a explicação do erro", async () => {
  await renderReader({
    "POST /tutor/word": { status: 429, body: { code: "llm_budget_exceeded" } },
  });

  await userEvent.click(screen.getByText("sat"));

  expect(await screen.findByRole("alert")).toHaveTextContent("teto mensal do tutor");
});

test("depois de uma falha do tutor, dá para tentar outra vez", async () => {
  let attempts = 0;
  await renderReader({
    "POST /tutor/word": () => {
      attempts += 1;
      return attempts === 1
        ? { status: 502, body: { code: "tutor_provider_error" } }
        : { body: SAT };
    },
  });
  await userEvent.click(screen.getByText("sat"));
  expect(await screen.findByRole("alert")).toHaveTextContent("O serviço do tutor falhou");

  await userEvent.click(screen.getByRole("button", { name: "Tentar outra vez" }));

  expect(await screen.findByText("sentou-se")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
});
