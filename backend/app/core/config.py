"""Configuração da aplicação, lida de variáveis de ambiente e do ficheiro .env."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Este ficheiro está em backend/app/core/config.py. Subir três níveis dá a pasta
# backend/ e subir quatro dá a raiz do repositório. Calcular os caminhos a partir
# do próprio ficheiro faz com que a app funcione igual seja qual for a pasta de
# onde é lançada.
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

# O servidor só escuta nesta morada. É uma constante e não uma opção de
# configuração de propósito: ninguém consegue expor a app à rede local por
# engano ao editar o .env (regra fixa 7 do CLAUDE.md).
SERVER_HOST = "127.0.0.1"


class Settings(BaseSettings):
    """Opções configuráveis. Cada campo lê a variável READER_<NOME_EM_MAIÚSCULAS>.

    O pydantic-settings procura primeiro nas variáveis de ambiente e depois no
    .env, e converte o texto para o tipo declarado (por exemplo "8000" para int).
    Um valor inválido dá erro logo no arranque, em vez de falhar mais tarde.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="READER_",
        # O .env vai ter chaves de fornecedores noutras fases; ignorar o que
        # esta classe ainda não conhece evita erros no arranque.
        extra="ignore",
    )

    data_dir: Path = REPO_ROOT / "data"
    port: int = 8000
    log_level: str = "INFO"

    # Fornecedor de voz. "fake" não faz chamadas externas nem gasta quota.
    speech_provider: Literal["fake", "azure"] = "fake"
    # Credenciais do Azure AI Speech, só necessárias com speech_provider="azure".
    # Aceitam os nomes habituais da Microsoft (AZURE_SPEECH_KEY) ou com o
    # prefixo da app. SecretStr esconde o valor se o objeto for impresso ou
    # registado por engano; para o usar é preciso chamar .get_secret_value().
    azure_speech_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_SPEECH_KEY", "READER_AZURE_SPEECH_KEY"),
    )
    azure_speech_region: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_SPEECH_REGION", "READER_AZURE_SPEECH_REGION"),
    )

    # Teto de caracteres sintetizados por mês. O valor por omissão é o
    # escalão gratuito do Azure AI Speech.
    monthly_tts_char_limit: int = 500_000
    # Preço usado só para estimar custos. Não foi confirmado na página oficial
    # do Azure; confirma-o antes de saíres do escalão gratuito.
    tts_usd_per_million_chars: float = 16.0

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        # Um caminho relativo como "./data" é interpretado a partir da raiz do
        # repositório, não da pasta onde o comando foi corrido.
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'reader.db'}"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
