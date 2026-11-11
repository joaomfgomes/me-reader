"""Interface de armazenamento de ficheiros."""

from typing import Protocol


class FileStorage(Protocol):
    """O que a aplicação precisa de um sítio para guardar ficheiros.

    Um Protocol descreve uma forma: qualquer classe com estes métodos serve,
    sem ter de herdar daqui. O resto da app depende só desta interface. Hoje a
    implementação é o disco (DiskStorage); numa versão web pode ser um serviço
    de armazenamento de objetos, sem mudar quem a usa.

    As chaves são nomes lógicos como "originals/ab12cd.epub", nunca caminhos
    do sistema de ficheiros.
    """

    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...
