import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./App";
import "./index.css";
import { PreferencesProvider } from "./lib/preferences";

// O QueryClient guarda a cache de todos os pedidos ao backend. Há um só para
// a aplicação inteira, disponibilizado aos componentes pelo Provider.
const queryClient = new QueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Falta o elemento #root no index.html");
}

createRoot(rootElement).render(
  // O StrictMode ativa verificações extra do React em desenvolvimento.
  // Os "providers" embrulham a app e dão a todos os componentes acesso à
  // cache de pedidos, às preferências e à navegação entre páginas.
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </PreferencesProvider>
    </QueryClientProvider>
  </StrictMode>,
);
