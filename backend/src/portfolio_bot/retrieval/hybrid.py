"""Hybrid retrieval: run several strategies and fuse their rankings into one.

Each strategy searches the whole corpus on its own, and none filters for another, since a
filter can only drop a chunk the next stage might have rescued. Their lists are merged by
reciprocal rank fusion: a chunk earns 1 / (rrf_k + rank) from every list it appears in,
and the totals decide the order.

Fusion reads ranks and ignores scores. A cosine similarity of 0.6 and a ts_rank_cd of 0.1
are on unrelated scales, but first place means the same thing in both lists. The effect
is that a chunk ranked well by two strategies usually beats one ranked first by only one,
which is a strength when the strategies agree on the right chunk and a weakness when they
agree on noise.
"""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_bot.retrieval.base import Provenance, RetrievalStrategy, ScoredChunk


def reciprocal_rank_fusion(lists: Sequence[Sequence[ScoredChunk]], rrf_k: int) -> list[ScoredChunk]:
    """Merge ranked lists into one, best first.

    A chunk's score is the sum of 1 / (rrf_k + rank) over the lists it appears in, where
    rank is its position in that list, counting from 1. Its provenance gathers what every
    contributing list recorded about it, in the order the lists were given. Equal totals
    are broken by chunk id, so the same input always gives the same order.
    """
    totals: dict[int, float] = {}
    provenance: dict[int, list[Provenance]] = {}
    chunks: dict[int, ScoredChunk] = {}

    for ranked in lists:
        for rank, result in enumerate(ranked, start=1):
            chunk_id = result.chunk.chunk_id
            totals[chunk_id] = totals.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            provenance.setdefault(chunk_id, []).extend(result.provenance)
            chunks.setdefault(chunk_id, result)

    order = sorted(totals, key=lambda chunk_id: (-totals[chunk_id], chunk_id))
    return [
        ScoredChunk(
            chunk=chunks[chunk_id].chunk,
            score=totals[chunk_id],
            provenance=tuple(provenance[chunk_id]),
        )
        for chunk_id in order
    ]


class HybridRetriever:
    """Fuses the rankings of two or more strategies.

    Each strategy is asked for `candidate_depth` results, or k if that is larger, before
    fusing. Asking each for only k would discard a chunk one strategy ranks just below the
    cut before the other strategy had any chance to lift it. The strategies run one after
    another; each takes milliseconds, and running them in parallel would cost a second
    connection to save time nobody would notice.
    """

    name = "hybrid"

    def __init__(
        self, strategies: Sequence[RetrievalStrategy], *, rrf_k: int, candidate_depth: int
    ) -> None:
        if len(strategies) < 2:
            raise ValueError("hybrid retrieval needs at least two strategies to fuse")
        self._strategies = list(strategies)
        self._rrf_k = rrf_k
        self._candidate_depth = candidate_depth

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        depth = max(self._candidate_depth, k)
        lists = [strategy.retrieve(query, depth) for strategy in self._strategies]
        return reciprocal_rank_fusion(lists, self._rrf_k)[:k]
