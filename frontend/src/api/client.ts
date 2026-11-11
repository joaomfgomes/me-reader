// Função base para falar com o backend. Todas as chamadas à API passam por aqui.

/**
 * Erro devolvido pela API no formato application/problem+json (RFC 9457).
 *
 * O campo "code" é estável e é por ele que a interface escolhe a mensagem a
 * mostrar (ver lib/messages.ts). O "title" e o "detail" são texto para pessoas
 * e podem mudar.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    title: string,
    readonly detail?: string,
  ) {
    super(title);
    this.name = "ApiError";
  }
}

export interface ApiResponse<T> {
  status: number;
  data: T;
}

/** Faz um pedido à API e devolve o estado HTTP e o corpo já convertido de JSON. */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  // Caminho relativo: o pedido vai para a origem da página e o proxy do Vite
  // reencaminha /api para o backend.
  const response = await fetch(`/api/v1${path}`, init);

  if (!response.ok) {
    // Se o corpo não for o JSON esperado (backend desligado, por exemplo),
    // ficamos com um erro genérico em vez de rebentar aqui.
    const problem = (await response.json().catch(() => null)) as {
      code?: string;
      title?: string;
      detail?: string;
    } | null;
    throw new ApiError(
      response.status,
      problem?.code ?? "unknown_error",
      problem?.title ?? `Erro HTTP ${response.status}`,
      problem?.detail,
    );
  }

  // 204 (sem conteúdo) é a resposta de um DELETE bem-sucedido: não há corpo.
  const data = response.status === 204 ? undefined : await response.json();
  return { status: response.status, data: data as T };
}

/** Atalho para enviar um corpo em JSON. */
export function jsonBody(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
