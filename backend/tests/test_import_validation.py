"""Testes da validação de ficheiros importados (regra fixa 8)."""

import pytest

from app.core.errors import ProblemError
from app.importing import validation
from app.importing.epub import parse_epub
from app.importing.validation import is_safe_member_name, validate_file_size
from tests.epub_factory import build_opf, make_epub, make_zip


def rejection_code(data: bytes) -> str:
    """Tenta ler o EPUB e devolve o "code" do erro com que foi recusado."""
    with pytest.raises(ProblemError) as error:
        parse_epub(data)
    return error.value.code


def test_valid_epub_is_accepted() -> None:
    assert len(parse_epub(make_epub()).chapters) == 2


def test_file_over_the_size_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch altera o limite só durante este teste, para não termos de
    # criar um ficheiro de 50 MB.
    monkeypatch.setattr(validation, "MAX_FILE_BYTES", 1000)

    validate_file_size(1000)
    with pytest.raises(ProblemError) as error:
        validate_file_size(1001)
    assert error.value.code == "file_too_large"
    assert error.value.status == 413


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"isto e texto simples com extensao .epub",
        b"%PDF-1.7 um PDF a fingir que e EPUB",
        # Começa como um ZIP, mas o resto é lixo.
        b"PK\x03\x04" + b"\x00" * 100,
    ],
)
def test_file_that_is_not_a_zip_is_rejected(data: bytes) -> None:
    assert rejection_code(data) == "unsupported_file_type"


def test_zip_without_mimetype_is_rejected() -> None:
    assert rejection_code(make_epub(overrides={"mimetype": None})) == "unsupported_file_type"


def test_zip_with_another_mimetype_is_rejected() -> None:
    # Um .docx também é um ZIP, mas não é um EPUB.
    data = make_epub(overrides={"mimetype": "application/vnd.oasis.opendocument.text"})

    assert rejection_code(data) == "unsupported_file_type"


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "OEBPS/../../evil.txt", "/etc/passwd", "..\\evil.txt", "C:\\evil.txt"],
)
def test_archive_with_path_traversal_entry_is_rejected(name: str) -> None:
    assert rejection_code(make_epub(overrides={name: "x"})) == "unsafe_archive"


@pytest.mark.parametrize("name", ["mimetype", "OEBPS/chapter1.xhtml", "OEBPS/a..b/c.html"])
def test_ordinary_member_names_are_safe(name: str) -> None:
    assert is_safe_member_name(name)


def test_zip_bomb_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "MAX_UNCOMPRESSED_BYTES", 1_000_000)
    # 5 MB de zeros comprimem para poucos KB: é assim que uma ZIP-bomba passa
    # num limite que só olhe para o tamanho do ficheiro.
    bomb = make_epub(overrides={"OEBPS/bomb.bin": b"\x00" * 5_000_000})

    assert len(bomb) < 50_000
    assert rejection_code(bomb) == "unsafe_archive"


def test_reading_the_same_file_many_times_counts_towards_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validation, "MAX_UNCOMPRESSED_BYTES", 1_000_000)
    # Um só capítulo de 300 KB cabe no limite, mas a spine manda lê-lo dez vezes.
    chapter = {"big.xhtml": "<p>" + "word " * 60_000 + "</p>"}
    data = make_epub(chapter, spine=["big.xhtml"] * 10)

    assert rejection_code(data) == "unsafe_archive"


def test_archive_with_too_many_entries_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "MAX_ARCHIVE_ENTRIES", 10)
    extra = {f"OEBPS/extra{index}.txt": "x" for index in range(20)}

    assert rejection_code(make_epub(overrides=extra)) == "unsafe_archive"


def test_spine_pointing_outside_the_epub_is_rejected() -> None:
    opf = build_opf(["../../../etc/passwd"])

    assert rejection_code(make_epub(overrides={"OEBPS/content.opf": opf})) == "unsafe_archive"


def test_epub_without_container_is_rejected() -> None:
    data = make_epub(overrides={"META-INF/container.xml": None})

    assert rejection_code(data) == "invalid_epub"


def test_epub_with_broken_xml_is_rejected() -> None:
    data = make_epub(overrides={"OEBPS/content.opf": "<package><metadata>"})

    assert rejection_code(data) == "invalid_epub"


def test_epub_with_missing_chapter_file_is_rejected() -> None:
    data = make_epub(overrides={"OEBPS/chapter2.xhtml": None})

    assert rejection_code(data) == "invalid_epub"


def test_xml_entity_bomb_is_rejected() -> None:
    # "Billion laughs": cada entidade expande-se em dez da anterior. Um parser
    # ingénuo gastaria gigabytes de memória a expandir estas poucas linhas.
    bomb = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<package xmlns="http://www.idpf.org/2007/opf"><metadata>&c;</metadata></package>"""

    assert rejection_code(make_epub(overrides={"OEBPS/content.opf": bomb})) == "invalid_epub"


def test_plain_zip_helper_is_not_an_epub() -> None:
    assert rejection_code(make_zip({"readme.txt": "hello"})) == "unsupported_file_type"
