import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { App } from "./App";
import { mockApi, renderPage } from "./test/helpers";

const API = {
  "GET /documents": { body: { items: [], next_cursor: null } },
  "GET /health": {
    body: { status: "ok", checks: { database: "ok", data_dir: "ok", migrations: "ok" } },
  },
};

test("a página inicial é a biblioteca, com o estado do sistema no rodapé", async () => {
  mockApi(API);

  renderPage(<App />, { path: "*" });

  expect(await screen.findByRole("heading", { name: "Biblioteca" })).toBeInTheDocument();
  expect(await screen.findByText("Sistema saudável")).toBeInTheDocument();
});

test("escolher o tema escuro aplica-o à página e guarda a escolha", async () => {
  mockApi(API);
  renderPage(<App />, { path: "*" });
  // Sem preferência guardada nem sistema em modo escuro, começa em claro.
  expect(document.documentElement.dataset.theme).toBe("light");

  await userEvent.selectOptions(screen.getByLabelText("Tema"), "Escuro");

  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(JSON.parse(localStorage.getItem("reader.preferences") ?? "{}").theme).toBe("dark");
});

test("a preferência guardada é aplicada ao abrir a app", async () => {
  localStorage.setItem("reader.preferences", JSON.stringify({ theme: "dark", fontSize: 24 }));
  mockApi(API);

  renderPage(<App />, { path: "*" });

  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(screen.getByLabelText("Tema")).toHaveValue("dark");
});
