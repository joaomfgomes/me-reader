"""Verificação manual do fornecedor de voz configurado: "make voice-check".

Sintetiza uma frase difícil por língua (números, abreviaturas, hífenes,
apóstrofos, símbolos) e confirma que os tempos devolvidos apontam para as
palavras certas. Com o Azure, gasta cerca de 400 caracteres da quota.

Não faz parte dos testes automáticos, que nunca fazem chamadas pagas (regra
fixa 5). As frases foram escritas para este fim; não vêm de nenhum documento.
"""

import sys

from app.audio.alignment import align_timings
from app.audio.voice import SpeechProviderError
from app.core.config import Settings
from app.importing.segmentation import build_blocks
from app.providers import create_speech_synthesizer

SENTENCES = {
    "en": "Dr. Smith's well-known book, printed in 1865, cost $3.50 & sold 2,000 copies.",
    "es": "El Sr. García llegó a las 8:30 p. m. y preguntó: «¿Dónde está el n.º 12?»",
    "fr": "Aujourd'hui, l'homme qu'elle a vu – M. Dupont – a payé 1 250 € pour l'arc-en-ciel.",
    "de": "Z. B. kostet das 20-seitige Heft am 3. Mai nur 4,99 € – wirklich großartig!",
    "it": "L'amico dell'ing. Rossi arrivò alle 9.15: «Dov'è il n. 7?», chiese all'improvviso.",
}


def main() -> int:
    settings = Settings()
    speech = create_speech_synthesizer(settings)
    print(f"Fornecedor: {speech.name}")
    failures = 0

    for language, text in SENTENCES.items():
        voice = speech.voice_for(language)
        try:
            result = speech.synthesize(text, voice)
        except SpeechProviderError as exc:
            print(f"[{language}] FALHOU ({voice}): {exc}")
            failures += 1
            continue

        # As mesmas palavras que a importação calcularia para este texto.
        (block,) = build_blocks([text], language)
        words = [word for sentence in block.sentences for word in sentence.words]
        aligned = align_timings(words, result.timings)
        untimed = [text[word.start : word.end] for word in aligned if word.start_ms is None]
        starts = [word.start_ms for word in aligned if word.start_ms is not None]
        in_order = starts == sorted(starts)
        ok = not untimed and in_order and len(result.audio) > 0
        failures += 0 if ok else 1

        print(
            f"[{language}] {'ok' if ok else 'PROBLEMA'}  voz={voice}  "
            f"áudio={len(result.audio)} bytes ({result.media_type})  "
            f"duração={result.duration_ms} ms  palavras={len(words)}  "
            f"tempos do serviço={len(result.timings)}"
        )
        if untimed:
            print(f"      palavras sem tempo: {untimed}")
        if not in_order:
            print("      os tempos não estão por ordem")
        # Mostra a que pedaço de texto corresponde cada tempo do serviço.
        pieces = [text[t.text_offset : t.text_offset + t.length] for t in result.timings]
        print(f"      o serviço dividiu em: {pieces}")

    print("Tudo certo." if failures == 0 else f"{failures} língua(s) com problemas.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
