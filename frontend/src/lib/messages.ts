// Texto da interface que depende de valores vindos da API.

import { ApiError } from "../api/client";

/** As cinco línguas que a app ensina, pelo código que o backend usa. */
export const LANGUAGE_NAMES: Record<string, string> = {
  en: "Inglês",
  es: "Espanhol",
  fr: "Francês",
  de: "Alemão",
  it: "Italiano",
};

// Mensagem para cada "code" de erro da API. Cada uma diz o que aconteceu e,
// quando há alguma coisa a fazer, o que fazer a seguir.
const ERROR_MESSAGES: Record<string, string> = {
  file_too_large: "O ficheiro é demasiado grande. O limite é de 50 MB.",
  unsupported_file_type: "O ficheiro não é um EPUB. Escolhe um ficheiro .epub.",
  unsafe_archive: "O ficheiro foi recusado por segurança: a estrutura interna não é a de um livro.",
  invalid_epub: "O EPUB está danificado ou não tem texto. Experimenta outra edição do livro.",
  document_not_found: "Este livro já não está na biblioteca.",
  chapter_not_found: "O livro não tem esse capítulo.",
  unsupported_language: "Essa língua não é suportada.",
  language_required:
    "Este livro não tem língua definida. Escolhe-a na biblioteca para o poderes ouvir e pedir explicações.",
  llm_budget_exceeded:
    "Atingiste o teto mensal do tutor. As explicações já pedidas continuam disponíveis; as novas voltam no início do próximo mês.",
  tutor_provider_error: "O serviço do tutor falhou. Tenta outra vez daqui a pouco.",
  tutor_invalid_response:
    "O tutor não conseguiu dar uma explicação utilizável para esta palavra. Tenta outra vez.",
  sentence_not_found: "Este texto já não existe. Volta à biblioteca e abre o livro outra vez.",
  word_not_in_sentence: "Não foi possível identificar a palavra. Carrega nela outra vez.",
  vocabulary_entry_not_found: "Essa palavra já não está no vocabulário.",
  tts_quota_exceeded:
    "Atingiste o teto mensal de voz. O áudio já gerado continua a tocar; o resto fica disponível no início do próximo mês.",
  tts_provider_error: "O serviço de voz falhou. Tenta outra vez daqui a pouco.",
  block_not_found: "Este texto já não existe. Volta à biblioteca e abre o livro outra vez.",
  playback_failed: "O browser não conseguiu tocar o áudio. Tenta outra vez.",
};

const FALLBACK_MESSAGE =
  "Não foi possível falar com o servidor. Confirma que a aplicação está a correr (make dev).";

/** Converte qualquer erro numa frase para mostrar ao utilizador. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return ERROR_MESSAGES[error.code] ?? error.detail ?? error.message;
  }
  return FALLBACK_MESSAGE;
}
