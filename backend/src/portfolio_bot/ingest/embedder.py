"""Turn text into vectors.

An embedding model reads a piece of text and outputs a fixed-length list of numbers, 384
of them for bge-small, positioned so that texts with similar meaning land close together.
Retrieval later embeds the question the same way and looks for the chunks whose vectors
are nearest to it.

Two implementations share one protocol. The real one loads the model; the fake one derives
a vector from a hash of the text, so every test not specifically about embedding runs
without downloading a model and still gets the same vector for the same text every time.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# Properties of bge-small-en-v1.5, not settings. The width is also written into the schema
# as vector(384), so changing models to one with a different width is a migration.
EMBEDDING_DIMENSION = 384
# The model reads at most this many tokens and silently ignores the rest.
EMBEDDING_MAX_TOKENS = 512


class Embedder(Protocol):
    """Anything that can embed text, and say which model produced the vectors."""

    @property
    def model_name(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One unit-length vector per text, in order. For chunks, at ingest."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """One unit-length vector for a question, comparable with the chunks' vectors."""
        ...

    def count_tokens(self, texts: list[str]) -> list[int]:
        """How many tokens the model sees for each text, before any truncation."""
        ...


class SentenceTransformerEmbedder:
    """bge-small through sentence-transformers, pinned to one revision.

    The model is loaded on first use rather than at construction, so building an embedder
    for a run that turns out to have nothing to embed costs nothing.

    `query_instruction` is put in front of a question, and never in front of a chunk,
    before embedding it. bge was trained on (question, passage that answers it) pairs in
    which only the question carried this sentence, and it learned to place a prefixed
    question near its answer rather than near other short questions. Empty means none.
    """

    def __init__(
        self,
        model_name: str,
        model_revision: str,
        batch_size: int,
        *,
        query_instruction: str = "",
    ) -> None:
        self._model_name = model_name
        self._model_revision = model_revision
        self._batch_size = batch_size
        self._query_instruction = query_instruction
        self._model: SentenceTransformer | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            # Imported here because importing it loads torch, which takes seconds and is
            # not needed by any command that does not embed.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name, revision=self._model_revision, device="cpu"
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Normalized to unit length here, once, at write time. On unit vectors cosine
        # similarity equals the dot product, because the division by the two lengths is a
        # division by 1. That makes pgvector's cosine distance a plain dot product at query
        # time, and makes every stored vector directly comparable with every other.
        vectors = self._load().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([self._query_instruction + text])[0]

    def count_tokens(self, texts: list[str]) -> list[int]:
        tokenizer = self._load().tokenizer
        return [len(ids) for ids in tokenizer(texts, truncation=False)["input_ids"]]


class FakeEmbedder:
    """Deterministic vectors from a hash of the text, for tests.

    Equal texts get equal vectors and different texts get unrelated ones. The vectors carry
    no meaning, so nothing about retrieval quality can be tested with them, only plumbing.
    """

    def __init__(self, model_name: str = "fake", model_revision: str = "0") -> None:
        self._model_name = model_name
        self._model_revision = model_revision

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        # No instruction, so a test can find a chunk by querying with exactly the text that
        # chunk was embedded from.
        return _hash_vector(text)

    def count_tokens(self, texts: list[str]) -> list[int]:
        return [len(text.split()) for text in texts]


def _hash_vector(text: str) -> list[float]:
    raw = b""
    counter = 0
    while len(raw) < EMBEDDING_DIMENSION * 4:
        raw += hashlib.sha256(f"{counter}:{text}".encode()).digest()
        counter += 1
    integers = struct.unpack(f"<{EMBEDDING_DIMENSION}I", raw[: EMBEDDING_DIMENSION * 4])
    values = [value / 2**31 - 1.0 for value in integers]
    length = math.sqrt(sum(value * value for value in values))
    return [value / length for value in values]
