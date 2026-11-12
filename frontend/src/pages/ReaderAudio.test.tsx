import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { BlockAudio } from "../api/audio";
import type { ChapterDetail, DocumentDetail } from "../api/documents";
import { mockApi, renderPage, type ApiCall } from "../test/helpers";
import { ReaderPage } from "./ReaderPage";

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
  chapters: [{ position: 0, title: null }],
  reading_position: null,
};

// Dois blocos de uma frase cada, com as posições das palavras.
//                      0123456789012
const CHAPTER: ChapterDetail = {
  document_id: 1,
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
    {
      id: 6,
      position: 1,
      text: "The dog slept.",
      sentences: [
        {
          id: 20,
          position: 0,
          text: "The dog slept.",
          start_offset: 0,
          end_offset: 14,
          words: [[0, 3], [4, 7], [8, 13]],
        },
      ],
    },
  ],
};

function audioFor(blockId: number, hash: string, wordStarts: number[][]): BlockAudio {
  return {
    block_id: blockId,
    audio_url: `/api/v1/audio/${hash}`,
    media_type: "audio/wav",
    duration_ms: 6000,
    voice: "fake-en",
    cached: false,
    words: wordStarts.map(([start, end, startMs]) => ({
      start,
      end,
      start_ms: startMs,
      end_ms: startMs + 400,
    })),
  };
}

// Cada palavra dura 400 ms e começa de 500 em 500 ms.
const AUDIO_5 = audioFor(5, "aaa", [
  [0, 3, 0], [4, 7, 500], [8, 11, 1000], [13, 15, 2000], [16, 19, 2500], [20, 24, 3000],
]);
const AUDIO_6 = audioFor(6, "bbb", [[0, 3, 0], [4, 7, 500], [8, 13, 1000]]);

function routes(overrides: Parameters<typeof mockApi>[0] = {}) {
  return {
    "GET /documents/1": { body: DOCUMENT },
    "GET /documents/1/chapters/0": { body: CHAPTER },
    "PUT /documents/1/position": {
      body: { sentence_id: 11, block_id: 5, chapter_position: 0, updated_at: "x" },
    },
    "POST /blocks/5/audio": { body: AUDIO_5 },
    "POST /blocks/6/audio": { body: AUDIO_6 },
    ...overrides,
  };
}

async function renderReader(overrides?: Parameters<typeof mockApi>[0]): Promise<ApiCall[]> {
  const calls = mockApi(routes(overrides));
  renderPage(<ReaderPage />, { path: "/documents/:id", url: "/documents/1" });
  await screen.findByText("cat");
  return calls;
}

function audioElement(): HTMLAudioElement {
  const audio = document.querySelector("audio");
  if (!audio) {
    throw new Error("Falta o elemento <audio>");
  }
  return audio;
}

/** Finge que o áudio chegou a um dado instante, como o browser faria. */
function moveAudioTo(seconds: number) {
  const audio = audioElement();
  audio.currentTime = seconds;
  audio.dispatchEvent(new Event("timeupdate"));
}

function audioRequests(calls: ApiCall[]): ApiCall[] {
  return calls.filter((call) => call.path.endsWith("/audio"));
}

test("cada palavra tem o seu elemento e o texto continua igual", async () => {
  await renderReader();

  const sentence = document.querySelector('[data-sentence-id="11"]');
  expect(sentence).toHaveTextContent("The cat sat.");
  expect(sentence?.querySelectorAll("[data-word-key]")).toHaveLength(3);
  expect(screen.getByText("cat")).toHaveAttribute("data-word-key", "5-4");
});

test("ouvir pede o áudio do primeiro bloco e começa a tocar", async () => {
  const calls = await renderReader();

  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  expect(await screen.findByRole("button", { name: "Pausar" })).toBeInTheDocument();
  expect(audioRequests(calls)).toEqual([
    { method: "POST", path: "/blocks/5/audio", body: { confirm_private: false } },
  ]);
  expect(audioElement().src).toContain("/api/v1/audio/aaa");
  expect(audioElement().play).toHaveBeenCalled();
  expect(screen.getByText(/Voz simulada/)).toBeInTheDocument();
});

test("o destaque acompanha o áudio, palavra a palavra e frase a frase", async () => {
  await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  moveAudioTo(0.6);

  expect(screen.getByText("cat")).toHaveClass("word-now");
  expect(document.querySelector('[data-word-key="5-0"]')).not.toHaveClass("word-now");
  await waitFor(() =>
    expect(document.querySelector('[data-sentence-id="11"]')).toHaveClass("sentence-now"),
  );

  moveAudioTo(2.6);

  // Só uma palavra acesa de cada vez, agora na segunda frase.
  expect(document.querySelectorAll(".word-now")).toHaveLength(1);
  expect(screen.getByText("was")).toHaveClass("word-now");
  await waitFor(() =>
    expect(document.querySelector('[data-sentence-id="12"]')).toHaveClass("sentence-now"),
  );
  expect(document.querySelector('[data-sentence-id="11"]')).not.toHaveClass("sentence-now");
});

test("a posição guardada passa a ser a frase que está a ser dita", async () => {
  const calls = await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  moveAudioTo(2.6);

  await waitFor(() =>
    expect(calls).toContainEqual({
      method: "PUT",
      path: "/documents/1/position",
      body: { sentence_id: 12 },
    }),
  );
});

test("clicar numa frase toca a partir dela", async () => {
  await renderReader();

  await userEvent.click(screen.getByText("warm"));

  await screen.findByRole("button", { name: "Pausar" });
  // A segunda frase começa aos 2 segundos do áudio do bloco.
  expect(audioElement().currentTime).toBe(2);
});

test("os botões saltam entre frases, mudando de bloco quando é preciso", async () => {
  const calls = await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  await userEvent.click(screen.getByRole("button", { name: "Frase seguinte" }));
  expect(audioElement().currentTime).toBe(2);

  await userEvent.click(screen.getByRole("button", { name: "Frase seguinte" }));
  await waitFor(() => expect(audioElement().src).toContain("/api/v1/audio/bbb"));
  expect(audioRequests(calls).map((call) => call.path)).toEqual([
    "/blocks/5/audio",
    "/blocks/6/audio",
  ]);

  await userEvent.click(screen.getByRole("button", { name: "Frase anterior" }));
  await waitFor(() => expect(audioElement().src).toContain("/api/v1/audio/aaa"));
  expect(audioElement().currentTime).toBe(2);
  // Voltar a um bloco já ouvido não faz novo pedido.
  expect(audioRequests(calls)).toHaveLength(2);
});

test("repetir volta ao início da frase em curso", async () => {
  await renderReader();
  await userEvent.click(screen.getByText("warm"));
  await screen.findByRole("button", { name: "Pausar" });
  moveAudioTo(3.2);

  await userEvent.click(screen.getByRole("button", { name: "Repetir frase" }));

  expect(audioElement().currentTime).toBe(2);
});

test("quando um bloco acaba, o seguinte começa sozinho, e o capítulo pára no fim", async () => {
  const calls = await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  audioElement().dispatchEvent(new Event("ended"));
  await waitFor(() => expect(audioElement().src).toContain("/api/v1/audio/bbb"));
  expect(audioRequests(calls)).toHaveLength(2);

  audioElement().dispatchEvent(new Event("ended"));
  expect(await screen.findByRole("button", { name: "Ouvir" })).toBeInTheDocument();
});

test("pausar e retomar não pede áudio outra vez", async () => {
  const calls = await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  await userEvent.click(await screen.findByRole("button", { name: "Pausar" }));
  await userEvent.click(await screen.findByRole("button", { name: "Ouvir" }));

  expect(await screen.findByRole("button", { name: "Pausar" })).toBeInTheDocument();
  expect(audioRequests(calls)).toHaveLength(1);
});

test("a velocidade é aplicada ao áudio e fica guardada", async () => {
  await renderReader();
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  await screen.findByRole("button", { name: "Pausar" });

  await userEvent.selectOptions(screen.getByLabelText("Velocidade"), "0,75x");

  expect(audioElement().playbackRate).toBe(0.75);
  expect(JSON.parse(localStorage.getItem("reader.preferences") ?? "{}").playbackRate).toBe(0.75);
});

test("documento privado pede confirmação antes de enviar o texto", async () => {
  // O backend recusa enquanto o pedido não trouxer a confirmação.
  const calls = await renderReader({
    "POST /blocks/5/audio": (call) =>
      (call.body as { confirm_private: boolean }).confirm_private
        ? { body: AUDIO_5 }
        : {
            status: 409,
            body: { code: "private_document_confirmation_required", characters: 25 },
          },
  });

  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("marcado como privado");
  expect(dialog).toHaveTextContent("25 caracteres");
  expect(audioElement().play).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "Enviar e ouvir" }));

  expect(await screen.findByRole("button", { name: "Pausar" })).toBeInTheDocument();
  expect(audioRequests(calls).map((call) => call.body)).toEqual([
    { confirm_private: false },
    { confirm_private: true },
  ]);
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

test("cancelar a confirmação não envia nada", async () => {
  const calls = await renderReader({
    "POST /blocks/5/audio": {
      status: 409,
      body: { code: "private_document_confirmation_required", characters: 25 },
    },
  });
  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  await userEvent.click(await screen.findByRole("button", { name: "Cancelar" }));

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(audioRequests(calls)).toHaveLength(1);
});

test("teto mensal atingido mostra a explicação", async () => {
  await renderReader({
    "POST /blocks/5/audio": { status: 429, body: { code: "tts_quota_exceeded" } },
  });

  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("teto mensal de voz");
  expect(screen.getByRole("button", { name: "Ouvir" })).toBeEnabled();
});

test("depois de uma falha do serviço de voz, ouvir tenta outra vez", async () => {
  let attempts = 0;
  await renderReader({
    "POST /blocks/5/audio": () => {
      attempts += 1;
      return attempts === 1
        ? { status: 502, body: { code: "tts_provider_error" } }
        : { body: AUDIO_5 };
    },
  });

  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("O serviço de voz falhou");

  await userEvent.click(screen.getByRole("button", { name: "Ouvir" }));

  expect(await screen.findByRole("button", { name: "Pausar" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("o painel de custo mostra a estimativa do capítulo e do livro", async () => {
  const estimate = {
    blocks_total: 2,
    blocks_cached: 0,
    characters_total: 39,
    characters_cached: 0,
    characters_to_synthesize: 39,
    estimated_cost_usd: 0.5,
    characters_used_this_month: 0,
    monthly_character_limit: 500000,
    exceeds_monthly_limit: false,
  };
  const calls = await renderReader({
    "POST /documents/1/audio/estimate": (call) =>
      "chapter_position" in (call.body as object)
        ? { body: estimate }
        : { body: { ...estimate, characters_to_synthesize: 161558, estimated_cost_usd: 2.58 } },
  });
  // A estimativa só é pedida quando o painel abre.
  expect(calls.some((call) => call.path.endsWith("/estimate"))).toBe(false);

  await userEvent.click(screen.getByRole("button", { name: "Ver o custo do áudio" }));

  const panel = await screen.findByRole("region", { name: "Custo do áudio" });
  await waitFor(() => expect(panel).toHaveTextContent("39 caracteres por gerar"));
  expect(panel).toHaveTextContent("161 558 caracteres por gerar");
});
