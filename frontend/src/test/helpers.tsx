// Ferramentas partilhadas pelos testes das páginas.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";

import { PreferencesProvider } from "../lib/preferences";

interface MockResponse {
  status?: number;
  body?: unknown;
}

/** Uma resposta fixa, ou uma função que a escolhe a partir do pedido. */
type MockRoute = MockResponse | ((call: ApiCall) => MockResponse);

export interface ApiCall {
  method: string;
  path: string;
  body: unknown;
}

/**
 * Substitui o fetch por um backend a fingir.
 *
 * "routes" associa "MÉTODO /caminho" (sem o prefixo /api/v1) à resposta a dar.
 * Devolve a lista dos pedidos feitos, para os testes confirmarem o que foi
 * enviado. Os testes nunca fazem pedidos de rede verdadeiros.
 */
export function mockApi(routes: Record<string, MockRoute>): ApiCall[] {
  const calls: ApiCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = String(input).replace("/api/v1", "");
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      const call = { method, path, body };
      calls.push(call);

      const configured = routes[`${method} ${path}`];
      const route = typeof configured === "function" ? configured(call) : configured;
      if (!route) {
        const problem = { code: "not_found", title: "Recurso não encontrado", status: 404 };
        return new Response(JSON.stringify(problem), { status: 404 });
      }
      const status = route.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(route.body), { status });
    }),
  );
  return calls;
}

/**
 * Desenha uma página com tudo o que ela espera à volta: cache de pedidos,
 * preferências e navegação. "path" é o padrão da rota (com ":id") e "url" o
 * endereço em que a app "está".
 */
export function renderPage(page: ReactElement, { path = "/", url = "/" } = {}) {
  // Um QueryClient novo por teste, para a cache de um não passar para o
  // outro, e sem novas tentativas, para os erros aparecerem logo.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        {/* O MemoryRouter guarda o endereço em memória; não precisa de browser. */}
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path={path} element={page} />
            <Route path="*" element={<p>outra página</p>} />
          </Routes>
        </MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  );
}
