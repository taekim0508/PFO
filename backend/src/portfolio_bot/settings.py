"""Every tunable value in the project, read once from the environment.

Nothing outside this module reads `os.environ` or hard-codes a value a reasonable person
would want to change.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env lives at the repository root. Resolving it from this file rather than from the
# working directory is what lets `pb` run from backend/ and `make ingest` run from the
# repository root and still read the same file.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Configuration for the whole project, loaded from the environment and .env."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # .env also carries POSTGRES_* values that only docker-compose reads.
        extra="ignore",
        # Without this, pydantic warns about the model_* field names below.
        protected_namespaces=(),
    )

    # Database. No default on purpose: a connection string committed to a tracked file
    # would break the secrets rule, so a missing DATABASE_URL fails at startup.
    database_url: str

    # Embeddings. The revision is pinned so an upstream change to the model cannot
    # silently alter the vectors already stored in the database.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"

    # Chunking, measured in characters, because the chunker splits on characters and
    # stores character offsets. bge-small truncates its input at 512 tokens, roughly
    # 2000 characters, so 1000 leaves room for the heading path prepended at ingest.
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Retrieval.
    top_k: int = 5
    rrf_k: int = 60

    # Generation. These three are what make the model layer provider-agnostic: Ollama,
    # Together, Groq, and Fireworks all speak the same shape, so switching is config.
    model_name: str = "qwen3.5:9b"
    model_base_url: str = "http://localhost:11434/v1"
    # No default, so deploying without a key fails at startup rather than at the first
    # user request. Ollama ignores the value it is sent, so any placeholder works locally.
    model_api_key: str

    # Logging.
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the settings, reading the environment exactly once per process.

    Cached so that every caller sees the same values. Without it, a change to the
    environment mid-process would leave two parts of the application disagreeing about
    something like top_k, with nothing in the logs to explain it.
    """
    return Settings()
