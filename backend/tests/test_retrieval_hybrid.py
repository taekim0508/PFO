"""Hybrid retrieval asks each strategy deep enough, fuses, and cuts to k."""

import pytest

from portfolio_bot.db.vector import vector_literal
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.retrieval.base import Provenance, RetrievalStrategy, RetrievedChunk, ScoredChunk
from portfolio_bot.retrieval.dense import DenseRetriever
from portfolio_bot.retrieval.hybrid import HybridRetriever
from portfolio_bot.retrieval.lexical import LexicalRetriever


class FixedStrategy:
    """Returns a fixed ranking, truncated to k, and records every k it was asked for."""

    def __init__(self, name, chunk_ids):
        self.name = name
        self._chunk_ids = chunk_ids
        self.asked_for = []

    def retrieve(self, query, k):
        self.asked_for.append(k)
        return [
            ScoredChunk(
                RetrievedChunk(chunk_id, 1, "doc.md", "Doc", (), chunk_id, "text", 0, 1),
                1.0,
                (Provenance(self.name, rank),),
            )
            for rank, chunk_id in enumerate(self._chunk_ids[:k], start=1)
        ]


def hybrid(*strategies, depth=20):
    return HybridRetriever(strategies, rrf_k=60, candidate_depth=depth)


def test_asks_each_strategy_for_the_candidate_depth():
    a, b = FixedStrategy("a", [1, 2]), FixedStrategy("b", [2, 1])

    hybrid(a, b, depth=20).retrieve("q", k=5)

    assert a.asked_for == b.asked_for == [20]


def test_asks_for_k_when_k_is_deeper_than_the_candidate_depth():
    a, b = FixedStrategy("a", [1]), FixedStrategy("b", [1])

    hybrid(a, b, depth=20).retrieve("q", k=50)

    assert a.asked_for == b.asked_for == [50]


def test_a_chunk_below_k_in_one_list_can_be_lifted_by_the_other():
    # Chunk 9 is 6th for a and 1st for b. Asking each for only k=2 would never have seen it
    # in a's list, and it would score 1/61 instead of 1/61 + 1/66.
    a = FixedStrategy("a", [1, 2, 3, 4, 5, 9])
    b = FixedStrategy("b", [9, 7])

    results = hybrid(a, b).retrieve("q", k=2)

    assert [r.chunk.chunk_id for r in results] == [9, 1]


def test_returns_at_most_k():
    a, b = FixedStrategy("a", [1, 2, 3]), FixedStrategy("b", [4, 5, 6])

    assert len(hybrid(a, b).retrieve("q", k=4)) == 4


def test_needs_at_least_two_strategies():
    with pytest.raises(ValueError):
        HybridRetriever([FixedStrategy("a", [])], rrf_k=60, candidate_depth=20)


def test_rejects_a_k_below_one():
    with pytest.raises(ValueError):
        hybrid(FixedStrategy("a", []), FixedStrategy("b", [])).retrieve("q", k=0)


def test_satisfies_the_retrieval_strategy_protocol():
    strategy = hybrid(FixedStrategy("a", []), FixedStrategy("b", []))

    assert isinstance(strategy, RetrievalStrategy)
    assert strategy.name == "hybrid"


@pytest.mark.database
def test_fuses_real_dense_and_lexical_results(db):
    """Over real Postgres, the chunk both arms find comes out on top."""
    embedder = FakeEmbedder(model_name="test", model_revision="1")
    document_id = db.execute(
        "INSERT INTO documents (source_path, title, content_hash) VALUES ('d.md', 'D', 'h') "
        "RETURNING id"
    ).fetchone()["id"]
    texts = ["The chatbot ranks results.", "Nothing matches here.", "A result."]
    ids = []
    for ordinal, text in enumerate(texts):
        chunk_id = db.execute(
            "INSERT INTO chunks (document_id, ordinal, text, token_count, char_start, char_end) "
            "VALUES (%s, %s, %s, 1, 0, 1) RETURNING id",
            (document_id, ordinal, text),
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO chunk_embeddings VALUES (%s, %s::vector, 'test', '1')",
            (chunk_id, vector_literal(embedder.embed([text])[0])),
        )
        ids.append(chunk_id)

    # The fake embeds a query exactly as it embeds a chunk, so dense ranks the first chunk
    # first; lexical also ranks it first, matching chatbot, rank, and result.
    strategy = HybridRetriever(
        [DenseRetriever(db, embedder, ef_search=40), LexicalRetriever(db)],
        rrf_k=60,
        candidate_depth=20,
    )
    top = strategy.retrieve(texts[0], k=3)[0]

    assert top.chunk.chunk_id == ids[0]
    assert top.provenance == (Provenance("dense", 1), Provenance("lexical", 1))
