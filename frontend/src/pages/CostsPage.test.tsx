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
    llm: {
      requests: 12,
      cache_hits: 3,
      cache_hit_rate: 0.25,
      input_tokens: 11250,
      output_tokens: 1800,
      estimated_cost_usd: 0.002,
      monthly_usd_limit: 2,
      usd_remaining: 1.998,
    },
  };
}

function withTutor(overrides: Partial<Usage["llm"]>): Usage {
  const base = usage(1468);
  return { ...base, llm: { ...base.llm, ...overrides } };
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
  expect(
    screen.getByRole("meter", { name: "Parte do teto mensal já usada" }),
  ).toHaveAttribute("value", "1468");
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

test("mostra o consumo do tutor: custo, consultas, cache e tokens", async () => {
  renderCosts(usage(1468));

  const section = (await screen.findByRole("heading", { name: "Tutor" })).closest("section");
  if (!section) {
    throw new Error("secção do tutor não encontrada");
  }
  // 0,002 USD: pouco, mas não zero.
  expect(section).toHaveTextContent("menos de 0,01 US$ de 2,00 US$");
  expect(section).toHaveTextContent("12");
  expect(section).toHaveTextContent("25%");
  // 11 250 tokens de entrada mais 1 800 de saída.
  expect(section).toHaveTextContent("13 050");
});

test("avisa a partir de 80% do teto do tutor", async () => {
  renderCosts(withTutor({ estimated_cost_usd: 1.7, usd_remaining: 0.3 }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Já usaste 85% do teto mensal do tutor");
});

test("diz que o teto do tutor foi atingido", async () => {
  renderCosts(withTutor({ estimated_cost_usd: 2.1, usd_remaining: 0 }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Atingiste o teto mensal do tutor");
});
