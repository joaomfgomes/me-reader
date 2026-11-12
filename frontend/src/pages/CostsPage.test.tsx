import { screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Usage } from "../api/audio";
import { mockApi, renderPage } from "../test/helpers";
import { CostsPage } from "./CostsPage";

function usage(characters: number, overrides: Partial<Usage["tts"]> = {}): Usage {
  return {
    month: "2026-11",
    tts: {
      requests: 4,
      cache_hits: 3,
      cache_hit_rate: 0.75,
      characters_synthesized: characters,
      characters_from_cache: 4404,
      estimated_cost_usd: 0.023488,
      monthly_character_limit: 500000,
      characters_remaining: 500000 - characters,
      ...overrides,
    },
  };
}

function renderCosts(data: Usage) {
  mockApi({ "GET /usage": { body: data } });
  renderPage(<CostsPage />);
}

test("mostra o consumo do mês, a cache e o custo estimado", async () => {
  renderCosts(usage(1468));

  expect(await screen.findByRole("heading", { name: "Voz em novembro de 2026" })).toBeVisible();
  expect(screen.getByText("1 468")).toBeInTheDocument();
  expect(screen.getByText(/Faltam 498 532 caracteres/)).toBeInTheDocument();
  expect(screen.getByText("75%")).toBeInTheDocument();
  expect(screen.getByText("4 404")).toBeInTheDocument();
  expect(screen.getByText(/0,02/)).toBeInTheDocument();
  expect(screen.getByRole("meter")).toHaveAttribute("value", "1468");
  // Longe do teto, não há avisos.
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("avisa a partir de 80% do teto mensal", async () => {
  renderCosts(usage(410000));

  expect(await screen.findByRole("alert")).toHaveTextContent("Já usaste 82% do teto mensal");
});

test("diz que o teto foi atingido e que a cache continua a tocar", async () => {
  renderCosts(usage(500000));

  expect(await screen.findByRole("alert")).toHaveTextContent("Atingiste o teto mensal");
});

test("sem pedidos, não inventa uma taxa de cache", async () => {
  renderCosts(usage(0, { requests: 0, cache_hits: 0, cache_hit_rate: null }));

  expect(await screen.findByText("Sem pedidos")).toBeInTheDocument();
});

test("avisa quando não consegue obter o consumo", async () => {
  mockApi({ "GET /usage": { status: 500, body: {} } });

  renderPage(<CostsPage />);

  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
