// Cliente das rotas /api/v1/documents.
//
// Os tipos espelham os esquemas do backend (backend/app/api/schemas.py).
// Se um mudar, o outro tem de mudar também.

import { apiRequest, jsonBody } from "./client";

export interface DocumentSummary {
  id: number;
  title: string;
  author: string | null;
  language: string | null;
  format: string;
  is_private: boolean;
  file_size: number;
  created_at: string;
  status: "ready";
}

export interface ChapterSummary {
  position: number;
  title: string | null;
}

export interface ReadingPosition {
  sentence_id: number;
  block_id: number;
  chapter_position: number;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  chapters: ChapterSummary[];
  reading_position: ReadingPosition | null;
}

export interface DocumentList {
  items: DocumentSummary[];
  next_cursor: string | null;
}

export interface Sentence {
  id: number;
  position: number;
  text: string;
  /** Posições no texto do bloco: block.text.slice(start_offset, end_offset). */
  start_offset: number;
  end_offset: number;
  words: [number, number][];
}

export interface Block {
  id: number;
  position: number;
  /** Parágrafos separados por "\n". */
  text: string;
  sentences: Sentence[];
}

export interface ChapterDetail {
  document_id: number;
  position: number;
  title: string | null;
  blocks: Block[];
}

export async function listDocuments(cursor?: string): Promise<DocumentList> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return (await apiRequest<DocumentList>(`/documents${query}`)).data;
}

export async function getDocument(id: number): Promise<DocumentDetail> {
  return (await apiRequest<DocumentDetail>(`/documents/${id}`)).data;
}

export interface UploadResult {
  document: DocumentSummary;
  /** false quando o ficheiro já estava na biblioteca. */
  created: boolean;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  // FormData constrói o formulário multipart. Não definimos o Content-Type:
  // o browser trata disso e junta-lhe o delimitador das partes.
  const form = new FormData();
  form.append("file", file);
  const { status, data } = await apiRequest<DocumentSummary>("/documents", {
    method: "POST",
    body: form,
  });
  // A API responde 201 se criou o documento e 200 se já existia.
  return { document: data, created: status === 201 };
}

export async function updateDocument(
  id: number,
  changes: { language?: string; is_private?: boolean },
): Promise<DocumentDetail> {
  return (await apiRequest<DocumentDetail>(`/documents/${id}`, jsonBody("PATCH", changes))).data;
}

export async function deleteDocument(id: number): Promise<void> {
  await apiRequest<void>(`/documents/${id}`, { method: "DELETE" });
}

export async function getChapter(documentId: number, position: number): Promise<ChapterDetail> {
  return (await apiRequest<ChapterDetail>(`/documents/${documentId}/chapters/${position}`)).data;
}

export async function savePosition(
  documentId: number,
  sentenceId: number,
): Promise<ReadingPosition> {
  const body = jsonBody("PUT", { sentence_id: sentenceId });
  return (await apiRequest<ReadingPosition>(`/documents/${documentId}/position`, body)).data;
}
