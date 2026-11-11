import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  // Lê as variáveis READER_* do .env que está na raiz do repositório, para o
  // frontend e o backend concordarem na porta sem a repetir em dois sítios.
  const env = loadEnv(mode, "..", "READER_");
  const backendPort = env.READER_PORT ?? "8000";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      // Tal como o backend, o servidor de desenvolvimento só escuta nesta máquina.
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      // O browser fala sempre com o Vite; os pedidos a /api são reencaminhados
      // por ele para o backend. Para o browser é tudo a mesma origem, e por
      // isso o backend não precisa de abrir CORS.
      proxy: {
        "/api": `http://127.0.0.1:${backendPort}`,
      },
    },
    test: {
      // jsdom simula um browser dentro do Node, o suficiente para desenhar
      // componentes React e inspecionar o resultado.
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
