"""Constrói EPUBs mínimos em memória para os testes.

Os testes de validação precisam de ficheiros estragados ou maliciosos de
maneiras muito específicas. Gerá-los em código mostra em cada teste o que o
ficheiro tem de errado e evita guardar binários suspeitos no repositório.
"""

import io
import zipfile

CONTAINER_XML = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

DEFAULT_CHAPTERS = {
    "chapter1.xhtml": "<h1>Chapter One</h1><p>The cat sat on the mat. It was warm.</p>",
    "chapter2.xhtml": "<h1>Chapter Two</h1><p>The dog slept by the door.</p>",
}


def build_opf(
    hrefs: list[str],
    *,
    spine: list[str] | None = None,
    title: str | None = "Livro de teste",
    author: str | None = "Autora de Teste",
    language: str | None = "en",
) -> str:
    """Gera o ficheiro OPF: metadados, manifest e spine."""
    metadata = "".join(
        f"<dc:{tag}>{value}</dc:{tag}>"
        for tag, value in (("title", title), ("creator", author), ("language", language))
        if value is not None
    )
    manifest = "".join(
        f'<item id="item{index}" href="{href}" media-type="application/xhtml+xml"/>'
        for index, href in enumerate(hrefs)
    )
    # Por omissão a spine segue a ordem do manifest. "spine" permite outra
    # ordem ou repetições, indicando os hrefs.
    spine_ids = [f"item{hrefs.index(href)}" for href in (spine if spine is not None else hrefs)]
    itemrefs = "".join(f'<itemref idref="{item_id}"/>' for item_id in spine_ids)
    return (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">{metadata}</metadata>'
        f"<manifest>{manifest}</manifest><spine>{itemrefs}</spine></package>"
    )


def make_zip(files: dict[str, bytes | str]) -> bytes:
    """Cria um ZIP em memória com os ficheiros dados, pela ordem dada."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_epub(
    chapters: dict[str, str] | None = None,
    *,
    overrides: dict[str, bytes | str | None] | None = None,
    **opf_options,
) -> bytes:
    """Cria um EPUB válido. "chapters" é {nome do ficheiro: HTML do corpo}.

    "overrides" substitui ou acrescenta ficheiros do ZIP pelo nome completo;
    com o valor None, o ficheiro é retirado. Serve para estragar um EPUB de
    uma maneira concreta.
    """
    chapters = DEFAULT_CHAPTERS if chapters is None else chapters
    files: dict[str, bytes | str | None] = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": CONTAINER_XML,
        "OEBPS/content.opf": build_opf(list(chapters), **opf_options),
    }
    for name, body in chapters.items():
        files[f"OEBPS/{name}"] = f"<html><head><title>x</title></head><body>{body}</body></html>"
    files.update(overrides or {})
    return make_zip({name: content for name, content in files.items() if content is not None})
