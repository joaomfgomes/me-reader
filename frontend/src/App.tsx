import { Route, Routes } from "react-router";

import { HealthStatus } from "./components/HealthStatus";
import { usePreferences, type Theme } from "./lib/preferences";
import { LibraryPage } from "./pages/LibraryPage";
import { ReaderPage } from "./pages/ReaderPage";

export function App() {
  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      <div className="flex-1">
        {/* Cada <Route> liga um endereço a uma página. ":id" é um parâmetro,
            lido na página com useParams(). */}
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/documents/:id" element={<ReaderPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
      <Footer />
    </div>
  );
}

function Footer() {
  const { preferences, setTheme } = usePreferences();
  return (
    <footer className="border-t border-rule">
      <div className="mx-auto flex max-w-5xl flex-wrap items-start justify-between gap-4 px-5 py-4 text-sm">
        <HealthStatus />
        <label className="flex items-center gap-2">
          <span className="text-pencil">Tema</span>
          <select
            className="rounded border border-rule bg-sheet px-2 py-1"
            value={preferences.theme}
            onChange={(event) => setTheme(event.target.value as Theme)}
          >
            <option value="system">Igual ao sistema</option>
            <option value="light">Claro</option>
            <option value="dark">Escuro</option>
          </select>
        </label>
      </div>
    </footer>
  );
}

function NotFound() {
  return (
    <main className="mx-auto max-w-2xl px-5 pt-16">
      <p>Esta página não existe.</p>
      <a href="/" className="mt-4 inline-block text-pen underline underline-offset-4">
        Voltar à biblioteca
      </a>
    </main>
  );
}
