// Cliente do endpoint GET /api/v1/health.

export type CheckStatus = "ok" | "error";

export interface HealthReport {
  healthy: boolean;
  /** Estado de cada verificação: database, data_dir e migrations. */
  checks: Record<string, CheckStatus>;
}

/**
 * Pergunta ao backend se o sistema está saudável.
 *
 * O backend responde 200 quando está tudo bem e 503 quando alguma verificação
 * falha. Os dois casos são respostas válidas e trazem o detalhe em "checks".
 * Qualquer outra coisa (backend desligado, erro inesperado) é lançada como
 * erro, para a interface mostrar que não conseguiu obter o estado.
 */
export async function fetchHealth(): Promise<HealthReport> {
  // Caminho relativo: o pedido vai para a origem da página e o proxy do Vite
  // reencaminha-o para o backend.
  const response = await fetch("/api/v1/health");
  const body: unknown = await response.json();

  if (hasChecks(body) && (response.ok || response.status === 503)) {
    return { healthy: response.ok, checks: body.checks };
  }
  throw new Error(`Resposta inesperada do servidor (HTTP ${response.status})`);
}

// "Type guard": se devolver true, o TypeScript passa a saber que o valor tem
// um campo "checks". Dados que vêm da rede são "unknown" até serem verificados.
function hasChecks(value: unknown): value is { checks: Record<string, CheckStatus> } {
  return (
    typeof value === "object" &&
    value !== null &&
    "checks" in value &&
    typeof value.checks === "object" &&
    value.checks !== null
  );
}
