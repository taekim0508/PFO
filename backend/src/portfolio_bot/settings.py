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
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


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

    # Connection pool. max_size stays deliberately small: Neon caps concurrent connections
    # on the plan this deploys to, and running several uvicorn workers multiplies this
    # number by the worker count, which is the usual way that cap gets blown. timeout is how
    # long a caller waits for a free connection before giving up, in seconds.
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_timeout: float = 30.0

    # Embeddings. The revision is pinned so an upstream change to the model cannot
    # silently alter the vectors already stored in the database.
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    # How many texts go through the model at once. Larger batches are faster up to the
    # point where they stop fitting in memory; 32 is comfortable on a laptop CPU.
    embedding_batch_size: int = 32
    # Put in front of a question, never a chunk, before embedding it. bge was trained with
    # this exact sentence on its questions, which is what teaches it to place a short
    # question near the longer passage that answers it. Empty turns it off.
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages: "

    # Corpus. The directory `pb ingest` mirrors into the database. Resolved from this file
    # for the same reason as ENV_FILE, so it does not depend on the working directory.
    content_dir: Path = REPO_ROOT / "content"

    # Chunking, measured in characters, because the chunker splits on characters and
    # stores character offsets. bge-small truncates its input at 512 tokens, roughly
    # 2000 characters, so 1000 leaves room for the heading path prepended at ingest.
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Retrieval.
    top_k: int = 5
    # How many candidates an HNSW search keeps on its shortlist as it walks the graph.
    # Wider finds the true nearest chunks more often and costs more distance computations.
    # It also caps how many rows the index can return, so the dense retriever raises it to
    # k when k is larger. 40 is pgvector's own default, written out so it is visible.
    hnsw_ef_search: int = 40
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
