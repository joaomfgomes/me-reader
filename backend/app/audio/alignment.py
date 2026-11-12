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
      fica com o início do primeiro e o fim do último;
    - o serviço dá um só tempo a "las 8:30 p. m." e para nós são cinco
      palavras: o intervalo é repartido por elas, em proporção da posição de
      cada uma dentro desse pedaço de texto. É uma estimativa, mas faz o
      destaque avançar pela expressão em vez de ficar parado numa palavra.

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
            piece_start, piece_end = _share_of(timings[cursor], start, end)
            start_ms = piece_start if start_ms is None else min(start_ms, piece_start)
            end_ms = piece_end if end_ms is None else max(end_ms, piece_end)
            cursor += 1
        aligned.append(TimedWord(start, end, start_ms, end_ms))
    return aligned


def _share_of(timing: WordTiming, start: int, end: int) -> tuple[int, int]:
    """A parte do intervalo de um tempo que cabe à palavra em [start, end).

    Se a palavra ocupa os caracteres 4 a 8 de um pedaço de 8 caracteres que
    dura 600 ms, cabe-lhe a segunda metade: de 300 a 600 ms.
    """
    if timing.length <= 0:
        return timing.start_ms, timing.end_ms
    duration = timing.end_ms - timing.start_ms
    # Posição da palavra dentro do pedaço, entre 0 (início) e 1 (fim).
    first = (max(start, timing.text_offset) - timing.text_offset) / timing.length
    last = (min(end, _end(timing)) - timing.text_offset) / timing.length
    return timing.start_ms + round(first * duration), timing.start_ms + round(last * duration)


def _end(timing: WordTiming) -> int:
    return timing.text_offset + timing.length
