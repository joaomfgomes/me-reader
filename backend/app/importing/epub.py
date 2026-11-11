"""Extração de metadados e texto de um EPUB.

Estrutura de um EPUB, por ordem de leitura:

1. META-INF/container.xml diz onde está o ficheiro OPF.
2. O OPF tem os metadados (título, autor, língua), o "manifest" (lista de
   todos os ficheiros, cada um com um id) e a "spine" (a ordem pela qual os
   ficheiros de texto devem ser lidos, referidos pelo id).
3. Cada ficheiro da spine é uma página XHTML com parte do livro.

Lemos o ZIP diretamente em vez de usar a biblioteca EbookLib porque esta tem
licença AGPL, o mesmo motivo pelo qual o projeto não usa o PyMuPDF.
"""

import posixpath
import warnings
from dataclasses import dataclass
from urllib.parse import unquote
from xml.etree.ElementTree import Element, ParseError

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from bs4.element import NavigableString, PreformattedString
from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from app.importing.cleaning import clean_text
from app.importing.validation import EpubArchive, invalid_epub, unsafe_archive

# As páginas de um EPUB são XHTML (HTML escrito com as regras do XML). Lemo-las
# com o parser de HTML de propósito, porque tolera páginas mal formadas; este
# aviso do BeautifulSoup só diz que reparou nisso.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

CONTAINER_PATH = "META-INF/container.xml"

# Em XML, os nomes dos elementos pertencem a um "namespace" identificado por
# um URI. Estes prefixos servem só para escrever as pesquisas de forma legível.
_NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}

_TEXT_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}

# Elementos cujo conteúdo não é texto do livro.
_SKIPPED_TAGS = frozenset(
    {
        "head", "script", "style", "template", "noscript", "nav", "svg", "math",
        "iframe", "object", "embed", "audio", "video", "img", "form", "button",
    }
)  # fmt: skip

# Elementos que começam um parágrafo novo. Todos os outros (i, b, span, a, ...)
# são "inline": o seu texto pertence ao parágrafo onde estão.
_BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "caption", "dd", "div",
        "dl", "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
        "h6", "header", "hr", "li", "main", "ol", "p", "pre", "section", "table",
        "td", "th", "tr", "ul",
    }
)  # fmt: skip

_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


@dataclass(frozen=True)
class RawChapter:
    """Um ficheiro da spine: título (se houver) e parágrafos de texto limpo."""

    title: str | None
    paragraphs: list[str]


@dataclass(frozen=True)
class EpubContent:
    title: str | None
    author: str | None
    declared_language: str | None
    chapters: list[RawChapter]


def parse_epub(data: bytes) -> EpubContent:
    """Valida o EPUB e devolve os metadados e o texto, capítulo a capítulo."""
    archive = EpubArchive(data)

    container = _parse_xml(archive.read(CONTAINER_PATH))
    rootfile = container.find(".//container:rootfile", _NS)
    opf_path = rootfile.get("full-path") if rootfile is not None else None
    if not opf_path or opf_path not in archive:
        raise invalid_epub("O EPUB não indica onde está o ficheiro de conteúdos.")

    opf = _parse_xml(archive.read(opf_path))
    # Os caminhos no OPF são relativos à pasta onde o próprio OPF está.
    opf_dir = posixpath.dirname(opf_path)

    # Manifest: id de cada ficheiro -> caminho dentro do ZIP.
    text_files: dict[str, str] = {}
    for item in opf.findall("opf:manifest/opf:item", _NS):
        item_id, href = item.get("id"), item.get("href")
        if item_id and href and item.get("media-type") in _TEXT_MEDIA_TYPES:
            text_files[item_id] = _resolve_href(opf_dir, href)

    chapters: list[RawChapter] = []
    for itemref in opf.findall("opf:spine/opf:itemref", _NS):
        # linear="no" marca conteúdo auxiliar (notas, respostas) fora do fluxo normal.
        path = text_files.get(itemref.get("idref", ""))
        if path is None or itemref.get("linear") == "no":
            continue
        chapter = _extract_chapter(archive.read(path))
        # Páginas sem texto (a capa, por exemplo) não contam como capítulo.
        if chapter.paragraphs:
            chapters.append(chapter)

    return EpubContent(
        title=_metadata_text(opf, "dc:title"),
        author=_metadata_text(opf, "dc:creator"),
        declared_language=_metadata_text(opf, "dc:language"),
        chapters=chapters,
    )


def _parse_xml(data: bytes) -> Element:
    # O defusedxml é um invólucro do parser de XML da biblioteca padrão que
    # recusa as construções perigosas: entidades que se expandem sem fim
    # ("billion laughs") e referências a ficheiros ou endereços externos.
    try:
        return SafeElementTree.fromstring(data)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise invalid_epub("Um dos ficheiros de estrutura do EPUB não é XML válido.") from exc


def _metadata_text(opf: Element, tag: str) -> str | None:
    element = opf.find(f"opf:metadata/{tag}", _NS)
    text = clean_text(element.text) if element is not None and element.text else ""
    return text or None


def _resolve_href(base_dir: str, href: str) -> str:
    """Converte um caminho relativo do OPF no nome do ficheiro dentro do ZIP."""
    # Tira a âncora ("cap1.html#sec2") e desfaz a codificação de URL ("%20").
    relative = unquote(href.split("#", 1)[0])
    path = posixpath.normpath(posixpath.join(base_dir, relative))
    # Depois de normalizado, um caminho que ainda comece por ".." aponta para
    # fora do EPUB.
    if path.startswith(("../", "/")) or path == "..":
        raise unsafe_archive("O EPUB refere um ficheiro fora de si próprio.")
    return path


def _extract_chapter(html: bytes) -> RawChapter:
    try:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.body or soup
        paragraphs = _collect_paragraphs(root)
        heading = root.find(_HEADING_TAGS)
        title = " ".join(_collect_paragraphs(heading)) if isinstance(heading, Tag) else ""
    except RecursionError as exc:
        # HTML com milhares de elementos uns dentro dos outros, que nenhum
        # livro verdadeiro tem.
        raise invalid_epub("Uma das páginas do EPUB tem uma estrutura inválida.") from exc
    return RawChapter(title=title or None, paragraphs=paragraphs)


def _collect_paragraphs(root: Tag) -> list[str]:
    """Percorre a árvore HTML e devolve só o texto, um item por parágrafo.

    É aqui que se cumpre a regra de nunca mostrar o HTML do livro tal como vem:
    o que sai desta função é texto simples, sem elementos nem atributos.
    """
    paragraphs: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        text = clean_text("".join(pending))
        pending.clear()
        if text:
            paragraphs.append(text)

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, Tag):
                if child.name in _SKIPPED_TAGS:
                    continue
                if child.name == "br":
                    pending.append("\n")
                elif child.name in _BLOCK_TAGS:
                    # Um elemento de bloco fecha o parágrafo em curso, antes e depois.
                    flush()
                    walk(child)
                    flush()
                else:
                    walk(child)
            # PreformattedString cobre comentários, DOCTYPE e instruções de
            # processamento, que não são texto do livro.
            elif isinstance(child, NavigableString) and not isinstance(child, PreformattedString):
                pending.append(str(child))

    walk(root)
    flush()
    return paragraphs
