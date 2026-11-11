"""Testes da extração de metadados e texto de um EPUB."""

from app.importing.cleaning import clean_text
from app.importing.epub import parse_epub
from tests.epub_factory import make_epub


def paragraphs_of(body: str) -> list[str]:
    return parse_epub(make_epub({"c.xhtml": body})).chapters[0].paragraphs


def test_metadata_is_read_from_the_opf() -> None:
    content = parse_epub(make_epub(title="Dom Casmurro", author="Machado de Assis", language="pt"))

    assert content.title == "Dom Casmurro"
    assert content.author == "Machado de Assis"
    assert content.declared_language == "pt"


def test_missing_metadata_becomes_none() -> None:
    content = parse_epub(make_epub(title=None, author=None, language=None))

    assert (content.title, content.author, content.declared_language) == (None, None, None)


def test_chapters_follow_the_spine_order_not_the_manifest_order() -> None:
    chapters = {"a.xhtml": "<h1>A</h1><p>First.</p>", "b.xhtml": "<h1>B</h1><p>Second.</p>"}

    content = parse_epub(make_epub(chapters, spine=["b.xhtml", "a.xhtml"]))

    assert [chapter.title for chapter in content.chapters] == ["B", "A"]


def test_pages_without_text_are_not_chapters() -> None:
    chapters = {"cover.xhtml": '<img src="cover.jpg" alt="Capa"/>', "c.xhtml": "<p>Text.</p>"}

    assert len(parse_epub(make_epub(chapters)).chapters) == 1


def test_chapter_title_comes_from_the_first_heading() -> None:
    body = "<h2>CHAPTER I.<br/>Down the <i>Rabbit</i>-Hole</h2><p>Alice was tired.</p>"

    chapter = parse_epub(make_epub({"c.xhtml": body})).chapters[0]

    assert chapter.title == "CHAPTER I. Down the Rabbit-Hole"


def test_chapter_without_heading_has_no_title() -> None:
    assert parse_epub(make_epub({"c.xhtml": "<p>Just text.</p>"})).chapters[0].title is None


def test_each_block_element_becomes_a_paragraph() -> None:
    body = "<h1>Title</h1><p>One.</p><div><p>Two.</p><blockquote>Three.</blockquote></div>"

    assert paragraphs_of(body) == ["Title", "One.", "Two.", "Three."]


def test_inline_elements_stay_in_the_same_paragraph() -> None:
    body = '<p>It was <i>very</i> <b>odd</b>, <a href="#n1">indeed</a>.</p>'

    assert paragraphs_of(body) == ["It was very odd, indeed."]


def test_text_directly_inside_a_container_is_kept() -> None:
    assert paragraphs_of("<div>Loose text<p>A paragraph.</p>more loose text</div>") == [
        "Loose text",
        "A paragraph.",
        "more loose text",
    ]


def test_scripts_styles_and_comments_are_dropped() -> None:
    body = (
        "<script>alert('xss')</script><style>p { color: red }</style>"
        "<!-- comentário --><p onclick=\"steal()\">Safe <img src='x' onerror='steal()'/>text.</p>"
    )

    assert paragraphs_of(body) == ["Safe text."]


def test_extracted_text_has_no_markup() -> None:
    # Regra fixa 8: o HTML do livro nunca passa tal como vem. O que estava
    # escrito como texto (&lt;b&gt;) continua a ser texto, não um elemento.
    body = "<p>Use the &lt;b&gt; tag &amp; enjoy.</p>"

    assert paragraphs_of(body) == ["Use the <b> tag & enjoy."]


def test_whitespace_and_line_breaks_are_normalised() -> None:
    body = "<p>\n  Line one\n  continues   here.<br/>Line two.\n</p>"

    assert paragraphs_of(body) == ["Line one continues here. Line two."]


def test_clean_text_removes_invisible_characters() -> None:
    # Hífen opcional a meio da palavra e espaço de largura zero.
    assert clean_text("incr­ível​ texto") == "incrível texto"


def test_clean_text_normalises_unicode_to_composed_form() -> None:
    decomposed = "café"  # "e" seguido de acento agudo combinatório

    assert clean_text(decomposed) == "café"
    assert len(clean_text(decomposed)) == 4
