// Cliente das rotas do tutor e do vocabulário.
// Os tipos espelham backend/app/api/schemas.py.

import { apiRequest, jsonBody } from "./client";

export interface WordExplanation {
  /** Forma de dicionário, na língua do texto. */
  lemma: string;
  part_of_speech: string;
  /** Tradução do sentido que a palavra tem na frase. */
  translation: string;
  definition: string;
  pronunciation: string;
  ipa: string;
}

export interface WordResponse {
  word: string;
  sentence_id: number;
  explanation: WordExplanation;
  /** true se a explicação veio da cache, sem custo. */
  cached: boolean;
  vocabulary_entry_id: number;
}

export interface VocabularyEntry {
  id: number;
  language: string;
  word: string;
  explanation: WordExplanation;
  /** A frase onde a palavra foi encontrada da primeira vez. */
  sentence_text: string;
  /** null se o documento já foi apagado. */
  document_id: number | null;
  lookup_count: number;
  created_at: string;
  updated_at: string;
}

export interface VocabularyList {
  items: VocabularyEntry[];
  next_cursor: string | null;
}

/**
 * Pede a explicação de uma palavra.
 *
 * A palavra é indicada pela posição no texto do bloco e não pelo texto: o
 * backend vai buscá-la ao documento, e assim só sai texto que lá está.
 */
export async function explainWord(request: {
  sentenceId: number;
  wordStart: number;
  wordEnd: number;
  confirmPrivate: boolean;
}): Promise<WordResponse> {
  const body = jsonBody("POST", {
    sentence_id: request.sentenceId,
    word_start: request.wordStart,
    word_end: request.wordEnd,
    confirm_private: request.confirmPrivate,
  });
  return (await apiRequest<WordResponse>("/tutor/word", body)).data;
}

export async function listVocabulary(options: {
  cursor?: string;
  language?: string;
}): Promise<VocabularyList> {
  // URLSearchParams trata de codificar os valores e de juntar os "&".
  const params = new URLSearchParams();
  if (options.language) {
    params.set("language", options.language);
  }
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const query = params.size > 0 ? `?${params}` : "";
  return (await apiRequest<VocabularyList>(`/vocabulary${query}`)).data;
}

export async function deleteVocabularyEntry(id: number): Promise<void> {
  await apiRequest<void>(`/vocabulary/${id}`, { method: "DELETE" });
}
