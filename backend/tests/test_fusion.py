"""Reciprocal rank fusion, checked against arithmetic done by hand.

No database and no retrievers: the input lists are built directly, so a wrong answer here
can only come from the fusion itself. The running example is two lists,

    dense    [x, y, z]
    lexical  [z, x]

which with rrf_k = 0 score as plain reciprocal ranks:

    x  1/1 + 1/2 = 1.5
    z  1/3 + 1/1 = 1.333...
    y  1/2       = 0.5
"""

import math

from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk
from portfolio_bot.retrieval.hybrid import reciprocal_rank_fusion

X, Y, Z = 1, 2, 3


def chunk(chunk_id):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        source_path="doc.md",
        title="Doc",
        heading_path=(),
        ordinal=chunk_id,
        text=f"chunk {chunk_id}",
        char_start=0,
        char_end=1,
    )


def ranked(strategy, chunk_ids, scores=None):
    """A strategy's result list, in the given order, with arbitrary scores."""
    scores = scores or [1.0 - 0.1 * i for i in range(len(chunk_ids))]
    return [
        ScoredChunk(chunk(chunk_id), score, (Provenance(strategy, rank),))
        for rank, (chunk_id, score) in enumerate(zip(chunk_ids, scores, strict=True), start=1)
    ]


def ids(results):
    return [r.chunk.chunk_id for r in results]


def test_sums_reciprocal_ranks_with_k_of_zero():
    fused = reciprocal_rank_fusion([ranked("dense", [X, Y, Z]), ranked("lexical", [Z, X])], 0)

    assert ids(fused) == [X, Z, Y]
    assert [r.score for r in fused] == [1.5, 1 / 3 + 1, 0.5]


def test_sums_reciprocal_ranks_with_k_of_sixty():
    fused = reciprocal_rank_fusion([ranked("dense", [X, Y, Z]), ranked("lexical", [Z, X])], 60)

    assert ids(fused) == [X, Z, Y]
    for result, expected in zip(fused, [1 / 61 + 1 / 62, 1 / 63 + 1 / 61, 1 / 62], strict=True):
        assert math.isclose(result.score, expected)


def test_ignores_the_strategies_own_scores():
    # Lexical scores z far above anything dense scored. Only ranks count, so the result is
    # the same as with ordinary scores.
    lists = [
        ranked("dense", [X, Y, Z], scores=[0.9, 0.8, 0.7]),
        ranked("lexical", [Z, X], scores=[500.0, 0.001]),
    ]

    assert ids(reciprocal_rank_fusion(lists, 0)) == [X, Z, Y]


def test_provenance_keeps_every_strategys_own_rank():
    fused = reciprocal_rank_fusion([ranked("dense", [X, Y, Z]), ranked("lexical", [Z, X])], 60)
    by_id = {r.chunk.chunk_id: r.provenance for r in fused}

    assert by_id[X] == (Provenance("dense", 1), Provenance("lexical", 2))
    assert by_id[Z] == (Provenance("dense", 3), Provenance("lexical", 1))
    assert by_id[Y] == (Provenance("dense", 2),)


def test_equal_totals_are_broken_by_chunk_id():
    # Each is first in exactly one list, so both score 1/61.
    fused = reciprocal_rank_fusion([ranked("dense", [Z]), ranked("lexical", [X])], 60)

    assert fused[0].score == fused[1].score
    assert ids(fused) == [X, Z]


def test_one_empty_list_leaves_the_other_in_its_own_order():
    fused = reciprocal_rank_fusion([ranked("dense", [Z, X, Y]), []], 60)

    assert ids(fused) == [Z, X, Y]


def test_nothing_in_gives_nothing_out():
    assert reciprocal_rank_fusion([[], []], 60) == []
