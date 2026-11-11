import { useQuery } from "@tanstack/react-query";

import { fetchHealth, type CheckStatus } from "../api/health";

// Texto mostrado para cada verificação que o backend devolve.
const CHECK_LABELS: Record<string, string> = {
  database: "A base de dados aceita escrita",
  data_dir: "A pasta de dados aceita escrita",
  migrations: "As migrações estão na última versão",
};

const REFRESH_INTERVAL_MS = 10_000;

export function HealthStatus() {
  // O TanStack Query trata de fazer o pedido, guardar o resultado e repeti-lo
  // de 10 em 10 segundos. "queryKey" identifica estes dados na cache dele.
  const { data, isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: REFRESH_INTERVAL_MS,
    // Sem novas tentativas automáticas: se o backend estiver em baixo,
    // queremos mostrá-lo já. O intervalo acima volta a tentar daí a pouco.
    retry: false,
  });

  if (isPending) {
    return <Panel tone="neutral" title="A verificar o sistema…" />;
  }

  if (isError) {
    return (
      <Panel tone="bad" title="Sem ligação ao servidor">
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
          Não foi possível obter o estado do sistema. Confirma que o backend está a correr
          (<code className="font-mono">make dev</code>).
        </p>
      </Panel>
    );
  }

  return (
    <Panel
      tone={data.healthy ? "good" : "bad"}
      title={data.healthy ? "Sistema saudável" : "Sistema com problemas"}
    >
      <ul className="mt-4 divide-y divide-stone-200 dark:divide-stone-800">
        {Object.entries(data.checks).map(([name, status]) => (
          <li key={name} className="flex items-center justify-between gap-4 py-3 text-sm">
            <span>{CHECK_LABELS[name] ?? name}</span>
            <CheckBadge status={status} />
          </li>
        ))}
      </ul>
      {!data.healthy && (
        <p className="mt-4 text-sm text-stone-600 dark:text-stone-400">
          Corre <code className="font-mono">make migrate</code> e confirma as permissões da pasta
          de dados.
        </p>
      )}
    </Panel>
  );
}

type Tone = "good" | "bad" | "neutral";

const DOT_COLORS: Record<Tone, string> = {
  good: "bg-emerald-500",
  bad: "bg-red-500",
  neutral: "bg-stone-400",
};

function Panel({
  tone,
  title,
  children,
}: {
  tone: Tone;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    // role="status" faz os leitores de ecrã anunciarem as mudanças de estado.
    <section
      role="status"
      className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900"
    >
      <h2 className="flex items-center gap-3 text-lg font-semibold">
        <span aria-hidden="true" className={`size-3 rounded-full ${DOT_COLORS[tone]}`} />
        {title}
      </h2>
      {children}
    </section>
  );
}

function CheckBadge({ status }: { status: CheckStatus }) {
  const ok = status === "ok";
  return (
    // O estado vai em texto e não só em cor, para não depender de distinguir
    // verde de vermelho.
    <span
      className={
        ok
          ? "font-medium text-emerald-700 dark:text-emerald-400"
          : "font-medium text-red-700 dark:text-red-400"
      }
    >
      {ok ? "OK" : "Falhou"}
    </span>
  );
}
