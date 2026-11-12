// Preferências de visualização: tema e tamanho de letra.
//
// Ficam guardadas no browser (localStorage) e não no backend: são gostos de
// quem está a ler neste ecrã, não dados da aplicação.

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "system" | "light" | "dark";

export interface Preferences {
  theme: Theme;
  /** Tamanho da letra do texto do livro, em píxeis. */
  fontSize: number;
  /** Velocidade do áudio: 1 é a normal. */
  playbackRate: number;
}

export const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5];

export const FONT_SIZE_MIN = 16;
export const FONT_SIZE_MAX = 28;
export const FONT_SIZE_STEP = 2;

const DEFAULTS: Preferences = { theme: "system", fontSize: 20, playbackRate: 1 };
const STORAGE_KEY = "reader.preferences";

function loadPreferences(): Preferences {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<Preferences>;
    const theme = ["system", "light", "dark"].includes(stored.theme ?? "")
      ? (stored.theme as Theme)
      : DEFAULTS.theme;
    const fontSize =
      typeof stored.fontSize === "number"
        ? Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, stored.fontSize))
        : DEFAULTS.fontSize;
    const playbackRate = PLAYBACK_RATES.includes(stored.playbackRate ?? NaN)
      ? (stored.playbackRate as number)
      : DEFAULTS.playbackRate;
    return { theme, fontSize, playbackRate };
  } catch {
    // Valor corrompido ou localStorage indisponível (modo privado, por
    // exemplo): usamos as predefinições em vez de falhar.
    return DEFAULTS;
  }
}

function systemPrefersDark(): boolean {
  // matchMedia pergunta ao browser pela preferência do sistema operativo.
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

interface PreferencesContextValue {
  preferences: Preferences;
  setTheme: (theme: Theme) => void;
  changeFontSize: (delta: number) => void;
  setPlaybackRate: (rate: number) => void;
}

// Um "contexto" do React disponibiliza um valor a todos os componentes dentro
// do Provider, sem o passar de pai para filho em cada nível.
const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  // A função passada ao useState só corre na primeira vez: lê o localStorage
  // uma vez, ao arrancar.
  const [preferences, setPreferences] = useState(loadPreferences);

  // Guarda as preferências sempre que mudam.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Sem localStorage as preferências valem só para esta sessão.
    }
  }, [preferences]);

  // Aplica o tema ao elemento <html>. As cores estão todas em variáveis CSS
  // que dependem deste atributo (ver index.css).
  useEffect(() => {
    const apply = () => {
      const dark =
        preferences.theme === "dark" || (preferences.theme === "system" && systemPrefersDark());
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();

    // Em modo "sistema", acompanha a mudança do sistema operativo (por
    // exemplo, quando o macOS passa a escuro ao anoitecer).
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener("change", apply);
    // A função devolvida por um efeito é a "limpeza": corre antes do efeito
    // seguinte e quando o componente sai do ecrã.
    return () => media?.removeEventListener("change", apply);
  }, [preferences.theme]);

  const value: PreferencesContextValue = {
    preferences,
    setTheme: (theme) => setPreferences((current) => ({ ...current, theme })),
    changeFontSize: (delta) =>
      setPreferences((current) => ({
        ...current,
        fontSize: Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, current.fontSize + delta)),
      })),
    setPlaybackRate: (playbackRate) => setPreferences((current) => ({ ...current, playbackRate })),
  };

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesContextValue {
  const value = useContext(PreferencesContext);
  if (!value) {
    throw new Error("usePreferences tem de ser usado dentro de um PreferencesProvider");
  }
  return value;
}
