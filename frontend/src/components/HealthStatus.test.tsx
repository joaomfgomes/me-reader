import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { HealthStatus } from "./HealthStatus";

// Substitui o fetch do browser por um falso que devolve a resposta que
// quisermos. Os testes nunca fazem pedidos de rede verdadeiros.
function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

function renderHealthStatus() {
  // Um QueryClient novo por teste, para a cache de um não passar para o outro.
  const queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <HealthStatus />
    </QueryClientProvider>,
  );
}

test("mostra o sistema saudável quando o backend responde ok", async () => {
  stubFetch(200, {
    status: "ok",
    checks: { database: "ok", data_dir: "ok", migrations: "ok" },
  });

  renderHealthStatus();

  // findByText espera até o texto aparecer (o pedido é assíncrono).
  expect(await screen.findByText("Sistema saudável")).toBeInTheDocument();
  expect(screen.getAllByText("OK")).toHaveLength(3);
  expect(fetch).toHaveBeenCalledWith("/api/v1/health");
});

test("mostra qual verificação falhou quando o backend responde 503", async () => {
  stubFetch(503, {
    type: "about:blank",
    title: "Sistema com problemas",
    status: 503,
    code: "health_check_failed",
    checks: { database: "ok", data_dir: "ok", migrations: "error" },
  });

  renderHealthStatus();

  expect(await screen.findByText("Sistema com problemas")).toBeInTheDocument();
  expect(screen.getAllByText("OK")).toHaveLength(2);
  expect(screen.getByText("Falhou")).toBeInTheDocument();
});

test("avisa quando não consegue falar com o backend", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }),
  );

  renderHealthStatus();

  expect(await screen.findByText("Sem ligação ao servidor")).toBeInTheDocument();
});
