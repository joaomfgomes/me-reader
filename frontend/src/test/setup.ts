// Corre antes de cada ficheiro de testes (ver "setupFiles" no vite.config.ts).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  // Remove do DOM simulado o que o teste desenhou e desfaz os "stubs" globais,
  // para um teste não influenciar o seguinte.
  cleanup();
  vi.unstubAllGlobals();
});
