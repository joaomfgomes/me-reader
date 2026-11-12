// Cliente das rotas de áudio, estimativa e consumo.
// Os tipos espelham backend/app/api/schemas.py.

import { apiRequest, jsonBody } from "./client";

export interface TimedWord {
  /** Posição da palavra no texto do bloco. */
  start: number;
  end: number;
  /** Quando é dita, em milissegundos. null se o serviço de voz não o disse. */
  start_ms: number | null;
  end_ms: number | null;
}

export interface BlockAudio {
  block_id: number;
  audio_url: string;
  media_type: string;
  duration_ms: number;
  voice: string;
  cached: boolean;
  /** Uma entrada por palavra do bloco, pela ordem em que aparecem no texto. */
  words: TimedWord[];
}

export interface AudioEstimate {
  blocks_total: number;
  blocks_cached: number;
  characters_total: number;
  characters_cached: number;
  characters_to_synthesize: number;
  estimated_cost_usd: number;
  characters_used_this_month: number;
  monthly_character_limit: number;
  exceeds_monthly_limit: boolean;
}

export interface Usage {
  /** Mês a que os números dizem respeito, no formato "2026-11". */
  month: string;
  tts: {
    requests: number;
    cache_hits: number;
    cache_hit_rate: number | null;
    characters_synthesized: number;
    characters_from_cache: number;
    estimated_cost_usd: number;
    monthly_character_limit: number;
    characters_remaining: number;
  };
}

/**
 * Pede o áudio de um bloco. O backend devolve-o da cache ou gera-o.
 *
 * confirmPrivate tem de ser true para gerar áudio novo de um documento
 * privado: é a confirmação de que o texto pode sair do portátil.
 */
export async function requestBlockAudio(
  blockId: number,
  confirmPrivate = false,
): Promise<BlockAudio> {
  const body = jsonBody("POST", { confirm_private: confirmPrivate });
  return (await apiRequest<BlockAudio>(`/blocks/${blockId}/audio`, body)).data;
}

/** Estimativa para um capítulo ou, sem capítulo, para o documento inteiro. */
export async function estimateAudio(
  documentId: number,
  chapterPosition?: number,
): Promise<AudioEstimate> {
  const body = jsonBody(
    "POST",
    chapterPosition === undefined ? {} : { chapter_position: chapterPosition },
  );
  return (await apiRequest<AudioEstimate>(`/documents/${documentId}/audio/estimate`, body)).data;
}

export async function getUsage(): Promise<Usage> {
  return (await apiRequest<Usage>("/usage")).data;
}
