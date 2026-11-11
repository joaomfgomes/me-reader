"""Deteção local da língua de um documento. Nada sai do portátil."""

from functools import lru_cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

# As cinco línguas que a app ensina, pelo código ISO 639-1.
SUPPORTED_LANGUAGES: dict[str, Language] = {
    "en": Language.ENGLISH,
    "es": Language.SPANISH,
    "fr": Language.FRENCH,
    "de": Language.GERMAN,
    "it": Language.ITALIAN,
}
_CODE_BY_LANGUAGE = {language: code for code, language in SUPPORTED_LANGUAGES.items()}

_SAMPLE_CHARS = 5000


@lru_cache(maxsize=1)
def _get_detector() -> LanguageDetector:
    # Limitar o detetor às cinco línguas torna-o mais rápido e mais certeiro
    # do que escolher entre as dezenas que a biblioteca conhece.
    # A "distância mínima" faz o detetor responder "não sei" (None) quando as
    # duas línguas mais prováveis estão muito próximas, em vez de arriscar.
    return (
        LanguageDetectorBuilder.from_languages(*SUPPORTED_LANGUAGES.values())
        .with_minimum_relative_distance(0.1)
        .build()
    )


def take_sample(paragraphs: list[str]) -> str:
    """Escolhe um excerto do meio do documento para a deteção.

    O início e o fim de um livro costumam ter texto que não é do livro e pode
    estar noutra língua: ficha técnica, licença, índice. Os livros do Project
    Gutenberg, por exemplo, abrem e fecham sempre com um aviso em inglês.
    """
    text = "\n".join(paragraphs)
    start = max(0, (len(text) - _SAMPLE_CHARS) // 2)
    return text[start : start + _SAMPLE_CHARS]


def detect_language(sample: str, declared: str | None = None) -> str | None:
    """Devolve o código da língua ("en", "es", ...) ou None se não for possível saber.

    Confiamos primeiro no texto, porque a língua declarada nos metadados de um
    EPUB está muitas vezes errada. A declarada serve de desempate quando o
    detetor não tem a certeza.
    """
    detected = _get_detector().detect_language_of(sample) if sample.strip() else None
    if detected is not None:
        return _CODE_BY_LANGUAGE[detected]

    # Os metadados trazem códigos como "en", "en-GB" ou "pt_BR"; só nos
    # interessa a primeira parte.
    code = (declared or "").replace("_", "-").split("-")[0].lower()
    return code if code in SUPPORTED_LANGUAGES else None
