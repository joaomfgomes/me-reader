// Corre antes de cada ficheiro de testes (ver "setupFiles" no vite.config.ts).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

beforeEach(() => {
  // O jsdom não toca áudio. Estes substitutos fazem o que interessa aos
  // testes: registam a chamada e disparam o evento que um browser dispararia.
  HTMLMediaElement.prototype.play = vi.fn(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  HTMLMediaElement.prototype.pause = vi.fn(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
  HTMLMediaElement.prototype.load = vi.fn();

  // O jsdom não implementa o scroll da janela; sem este substituto, cada
  // chamada escreveria um aviso no terminal.
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
});

afterEach(() => {
  // Remove do DOM simulado o que o teste desenhou e repõe o que foi alterado,
  // para um teste não influenciar o seguinte.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
