"""Armazenamento de ficheiros numa pasta do disco."""

import os
import re
import tempfile
from pathlib import Path

# Chaves aceites: segmentos de letras minúsculas, algarismos, ".", "_" e "-",
# separados por "/". Cada segmento começa por letra ou algarismo, o que exclui
# "..", ficheiros escondidos e caminhos absolutos.
_VALID_KEY = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*")


class DiskStorage:
    """Implementação de FileStorage que guarda cada chave como um ficheiro."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        # As chaves são geradas pela app, mas validamos na mesma: se um dia uma
        # chave for construída com dados de fora, não consegue sair da pasta.
        if not _VALID_KEY.fullmatch(key):
            raise ValueError("invalid storage key")
        return self._root / key

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atómica: escrevemos num ficheiro temporário e só no fim o
        # renomeamos para o nome final. Se a app for interrompida a meio, nunca
        # fica um ficheiro meio escrito com o nome certo.
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as temp_file:
                temp_file.write(data)
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
