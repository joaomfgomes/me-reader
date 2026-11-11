"""Testes do armazenamento em disco."""

from pathlib import Path

import pytest

from app.storage.disk import DiskStorage


@pytest.fixture
def storage(tmp_path: Path) -> DiskStorage:
    return DiskStorage(tmp_path / "files")


def test_saved_file_can_be_read_back(storage: DiskStorage) -> None:
    storage.save("originals/abc123.epub", b"conteudo")

    assert storage.exists("originals/abc123.epub")
    assert storage.read("originals/abc123.epub") == b"conteudo"


def test_saving_again_replaces_the_content(storage: DiskStorage) -> None:
    storage.save("a/b.bin", b"antigo")
    storage.save("a/b.bin", b"novo")

    assert storage.read("a/b.bin") == b"novo"


def test_save_leaves_no_temporary_files(storage: DiskStorage, tmp_path: Path) -> None:
    storage.save("a/b.bin", b"x")

    assert [path.name for path in (tmp_path / "files" / "a").iterdir()] == ["b.bin"]


def test_delete_removes_the_file_and_tolerates_missing_ones(storage: DiskStorage) -> None:
    storage.save("a/b.bin", b"x")

    storage.delete("a/b.bin")
    storage.delete("a/b.bin")

    assert not storage.exists("a/b.bin")


@pytest.mark.parametrize(
    "key",
    ["", "../fora.txt", "a/../../fora.txt", "/etc/passwd", "a//b", ".escondido", "a/.b", "A/b"],
)
def test_keys_that_could_leave_the_folder_are_rejected(storage: DiskStorage, key: str) -> None:
    with pytest.raises(ValueError):
        storage.save(key, b"x")
    with pytest.raises(ValueError):
        storage.read(key)
