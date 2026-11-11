import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

// Texto mostrado para cada verificação que o backend devolve.
const CHECK_LABELS: Record<string, string> = {
  database: "A base de dados aceita escrita",
  data_dir: "A pasta de dados aceita escrita",
  migrations: "As migrações estão na última versão",
};

const REFRESH_INTERVAL_MS = 10_000;

/** Indicador discreto do estado do sistema, para o rodapé. */
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
    return <Summary tone="neutral" title="A verificar o sistema…" />;
  }

  if (isError) {
    return (
      <div role="status">
        <Summary tone="bad" title="Sem ligação ao servidor" />
        <p className="mt-1 text-pencil">
          Confirma que o backend está a correr (<code>make dev</code>).
        </p>
      </div>
    );
  }

  return (
    // <details> é um elemento nativo que abre e fecha ao clicar no <summary>,
    // sem precisar de JavaScript nem de estado no React.
    <details role="status" open={!data.healthy}>
      <summary className="cursor-pointer list-none">
        <Summary
          tone={data.healthy ? "good" : "bad"}
          title={data.healthy ? "Sistema saudável" : "Sistema com problemas"}
        />
      </summary>
      <ul className="mt-2 space-y-1 text-pencil">
        {Object.entries(data.checks).map(([name, status]) => (
          <li key={name}>
            {CHECK_LABELS[name] ?? name}:{" "}
            {/* O estado vai em texto e não só em cor, para não depender de
                distinguir verde de vermelho. */}
            <span className={status === "ok" ? "text-ok" : "font-medium text-danger"}>
              {status === "ok" ? "OK" : "Falhou"}
            </span>
          </li>
        ))}
      </ul>
      {!data.healthy && (
        <p className="mt-2 text-pencil">
          Corre <code>make migrate</code> e confirma as permissões da pasta de dados.
        </p>
      )}
    </details>
  );
}

type Tone = "good" | "bad" | "neutral";

const DOT_COLORS: Record<Tone, string> = {
  good: "bg-ok",
  bad: "bg-danger",
  neutral: "bg-pencil",
};

function Summary({ tone, title }: { tone: Tone; title: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT_COLORS[tone]}`} />
      {title}
    </span>
  );
}
