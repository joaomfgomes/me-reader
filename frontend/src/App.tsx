import { HealthStatus } from "./components/HealthStatus";

export function App() {
  return (
    <main className="min-h-screen bg-stone-50 px-4 py-16 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <div className="mx-auto max-w-lg">
        <h1 className="text-3xl font-semibold tracking-tight">Leitor de línguas</h1>
        <p className="mt-2 mb-8 text-stone-600 dark:text-stone-400">
          Fase 0: o esqueleto está montado. A biblioteca e o leitor chegam na Fase 1.
        </p>
        <HealthStatus />
      </div>
    </main>
  );
}
