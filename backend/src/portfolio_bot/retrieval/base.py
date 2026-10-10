"""What every retrieval strategy promises, and the shape of what it returns.

Every strategy, dense, lexical, or a fusion of several, answers the same call with the
same type. That is what lets the search CLI, the evaluation harness, and the API swap one
for another by name, and what makes them comparable at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RetrievedChunk:
    """A stored chunk with enough of its document to show and cite it."""

    chunk_id: int
    document_id: int
    source_path: str
    title: str
    heading_path: tuple[str, ...]
    ordinal: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class Provenance:
    """One strategy's opinion of a chunk: which strategy, and where it ranked it, from 1."""

    strategy: str
    rank: int


@dataclass(frozen=True)
class ScoredChunk:
    """A chunk, the score that ordered it, and every strategy that put it in the list.

    `provenance` is a tuple because fusion combines several strategies' lists, and one
    fused result can owe its place to more than one of them. A single strategy produces
    one entry. The score's scale belongs to whichever strategy produced it, so scores from
    different strategies are not comparable with each other.
    """

    chunk: RetrievedChunk
    score: float
    provenance: tuple[Provenance, ...]


@runtime_checkable
class RetrievalStrategy(Protocol):
    """Turns a question into at most `k` chunks, best first."""

    @property
    def name(self) -> str: ...

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]: ...
