"""Validação de ficheiros importados, que nunca são de confiança (regra fixa 8).

Um EPUB é um ficheiro ZIP com páginas XHTML lá dentro. Antes de olharmos para
o conteúdo confirmamos que é mesmo um EPUB e que não foi construído para nos
fazer mal: demasiado grande, a descomprimir para um tamanho absurdo, ou com
nomes de ficheiros que tentam sair da pasta.
"""

import io
import zipfile
import zlib
from pathlib import PurePosixPath

from app.core.errors import ProblemError

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5_000

# Os primeiros bytes de qualquer ZIP com ficheiros lá dentro. Verificar esta
# "assinatura" é verificar o tipo pelo conteúdo, e não pela extensão do nome.
ZIP_SIGNATURE = b"PK\x03\x04"
EPUB_MIMETYPE = b"application/epub+zip"

_READ_CHUNK_BYTES = 64 * 1024


def file_too_large() -> ProblemError:
    limit_mb = MAX_FILE_BYTES // (1024 * 1024)
    return ProblemError(
        413, "file_too_large", "Ficheiro demasiado grande", f"O limite é de {limit_mb} MB."
    )


def unsupported_file_type(detail: str) -> ProblemError:
    return ProblemError(415, "unsupported_file_type", "Tipo de ficheiro não suportado", detail)


def unsafe_archive(detail: str) -> ProblemError:
    return ProblemError(422, "unsafe_archive", "Ficheiro recusado por segurança", detail)


def invalid_epub(detail: str) -> ProblemError:
    return ProblemError(422, "invalid_epub", "EPUB inválido", detail)


def validate_file_size(size: int) -> None:
    if size > MAX_FILE_BYTES:
        raise file_too_large()


def is_safe_member_name(name: str) -> bool:
    """Diz se o nome de um ficheiro dentro do ZIP fica dentro da "pasta" do ZIP.

    Nomes como "../../.ssh/authorized_keys" ou "/etc/passwd" servem para
    escrever fora da pasta de destino quando alguém extrai o ZIP sem cuidado
    (ataque conhecido como "zip slip"). Nós nunca extraímos para o disco, mas
    um ficheiro com nomes destes foi feito com má intenção e recusamo-lo todo.
    """
    if not name or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


class EpubArchive:
    """Acesso de leitura, com limites, aos ficheiros dentro de um EPUB.

    O conteúdo é sempre lido para memória e nunca extraído para o disco.
    """

    def __init__(self, data: bytes) -> None:
        if not data.startswith(ZIP_SIGNATURE):
            raise unsupported_file_type("O ficheiro não é um EPUB.")
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise unsupported_file_type("O ficheiro não é um EPUB válido.") from exc

        entries = self._zip.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise unsafe_archive("O ficheiro tem demasiadas entradas.")
        if not all(is_safe_member_name(entry.filename) for entry in entries):
            raise unsafe_archive("O ficheiro contém caminhos inválidos.")

        # Uma "ZIP-bomba" tem poucos KB comprimidos e muitos GB depois de
        # descomprimida. Primeira defesa: somar os tamanhos que o ZIP declara.
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
            raise unsafe_archive("O conteúdo descomprimido excede o limite.")

        self._names = {entry.filename for entry in entries}
        # Segunda defesa: contar os bytes que realmente saem da descompressão
        # (ver read()). Não depende do que o ZIP declara e apanha também o caso
        # de o livro mandar ler o mesmo ficheiro grande centenas de vezes.
        self._remaining_bytes = MAX_UNCOMPRESSED_BYTES

        # A norma EPUB obriga a um ficheiro "mimetype" com este conteúdo exato.
        # É o que distingue um EPUB de outro ZIP qualquer (um .docx, por exemplo).
        if "mimetype" not in self._names or self.read("mimetype").strip() != EPUB_MIMETYPE:
            raise unsupported_file_type("O ficheiro é um ZIP, mas não é um EPUB.")

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def read(self, name: str) -> bytes:
        """Lê um ficheiro do EPUB, descontando ao limite total de bytes descomprimidos."""
        if name not in self._names:
            raise invalid_epub("Falta um ficheiro que o EPUB diz ter.")

        chunks: list[bytes] = []
        try:
            with self._zip.open(name) as member:
                # Ler aos bocados permite parar a meio, sem chegar a ter em
                # memória um ficheiro gigante.
                while chunk := member.read(_READ_CHUNK_BYTES):
                    self._remaining_bytes -= len(chunk)
                    if self._remaining_bytes < 0:
                        raise unsafe_archive("O conteúdo descomprimido excede o limite.")
                    chunks.append(chunk)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as exc:
            # Dados corrompidos, compressão não suportada ou ficheiro cifrado.
            raise invalid_epub("Não foi possível ler um dos ficheiros do EPUB.") from exc
        return b"".join(chunks)
