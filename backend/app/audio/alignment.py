"""Liga os tempos devolvidos pelo serviço de voz às nossas palavras."""

from dataclasses import dataclass

from app.audio.voice import WordTiming


@dataclass(frozen=True)
class TimedWord:
    # Posição da palavra no texto do bloco, tal como foi calculada na importação.
    start: int
    end: int
    # Quando a palavra é dita. None se o serviço não devolveu nenhum tempo
    # que lhe corresponda.
    start_ms: int | None
    end_ms: int | None


def align_timings(words: list[tuple[int, int]], timings: list[WordTiming]) -> list[TimedWord]:
    """Dá a cada palavra nossa o intervalo de tempo em que é dita.

    A correspondência faz-se por sobreposição de posições no texto, nunca por
    ordem ou contagem (ADR-003). Exemplos do que isto resolve:

    - o serviço devolve "sat." com o ponto e a nossa palavra é "sat";
    - o serviço parte "rabbit-hole" em dois tempos e para nós é uma palavra:
      fica com o início do primeiro e o fim do último.

    As duas listas têm de vir ordenadas pela posição no texto.
    """
    aligned: list[TimedWord] = []
    index = 0
    for start, end in words:
        # Avança até ao primeiro tempo que não acaba antes desta palavra.
        # Como as listas estão ordenadas, nunca é preciso voltar atrás: o
        # trabalho total é proporcional ao tamanho das listas.
        while index < len(timings) and _end(timings[index]) <= start:
            index += 1

        start_ms: int | None = None
        end_ms: int | None = None
        cursor = index
        # Todos os tempos que começam antes de a palavra acabar sobrepõem-se a ela.
        while cursor < len(timings) and timings[cursor].text_offset < end:
            timing = timings[cursor]
            start_ms = timing.start_ms if start_ms is None else min(start_ms, timing.start_ms)
            end_ms = timing.end_ms if end_ms is None else max(end_ms, timing.end_ms)
            cursor += 1
        aligned.append(TimedWord(start, end, start_ms, end_ms))
    return aligned


def _end(timing: WordTiming) -> int:
    return timing.text_offset + timing.length
