"""Dense retrieval ranks stored chunks by cosine similarity to the question's vector.

Chunks are inserted by hand with chosen vectors, and the query's vector is chosen too, so
every expected score and order below is worked out by hand rather than taken from the
code under test. The vectors use only the first two of 384 coordinates:

    query      (1, 0)
    exact      (1, 0)       similarity  1.0
    near       (0.6, 0.8)   similarity  0.6
    unrelated  (0, 1)       similarity  0.0
    opposite   (-0.8, 0.6)  similarity -0.8
"""

import logging
import math

import pytest

from portfolio_bot.db.vector import vector_literal
from portfolio_bot.ingest.embedder import EMBEDDING_DIMENSION
from portfolio_bot.retrieval.base import Provenance, RetrievalStrategy
from portfolio_bot.retrieval.dense import HNSW_EF_SEARCH_MAX, DenseRetriever

pytestmark = pytest.mark.database

MODEL = "test-model"
REVISION = "1"


def plane(x, y):
    """A 384-wide vector with only its first two coordinates set."""
    return [x, y] + [0.0] * (EMBEDDING_DIMENSION - 2)


class FixedQueryEmbedder:
    """Embeds every question as the same chosen vector, so the expected ranking is known."""

    model_name = MODEL
    model_revision = REVISION

    def __init__(self, vector):
        self._vector = vector

    def embed_query(self, text):
        return self._vector


def store(db, title, text, vector, *, heading_path=(), model=MODEL, revision=REVISION):
    """Insert one document with one embedded chunk. Returns the chunk id."""
    document_id = db.execute(
        "INSERT INTO documents (source_path, title, content_hash) VALUES (%s, %s, 'h') "
        "RETURNING id",
        (f"{title.lower()}.md", title),
    ).fetchone()["id"]
    chunk_id = db.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, token_count, heading_path, char_start, char_end)
        VALUES (%s, 0, %s, 1, %s, 10, %s)
        RETURNING id
        """,
        (document_id, text, list(heading_path), 10 + len(text)),
    ).fetchone()["id"]
    db.execute(
        "INSERT INTO chunk_embeddings VALUES (%s, %s::vector, %s, %s)",
        (chunk_id, vector_literal(vector), model, revision),
    )
    return chunk_id


@pytest.fixture
def corpus(db):
    # Inserted out of order, so a correct ranking cannot come from insertion order.
    store(db, "Unrelated", "unrelated text", plane(0.0, 1.0))
    store(db, "Exact", "exact text", plane(1.0, 0.0), heading_path=("Section", "Sub"))
    store(db, "Opposite", "opposite text", plane(-0.8, 0.6))
    store(db, "Near", "near text", plane(0.6, 0.8))
    return db


def retriever(db, ef_search=40):
    return DenseRetriever(db, FixedQueryEmbedder(plane(1.0, 0.0)), ef_search=ef_search)


def test_ranks_by_cosine_similarity_with_hand_computed_scores(corpus):
    results = retriever(corpus).retrieve("anything", k=4)

    assert [r.chunk.title for r in results] == ["Exact", "Near", "Unrelated", "Opposite"]
    # Stored as 32-bit floats, so 0.6 comes back as 0.6000000238...
    for result, expected in zip(results, [1.0, 0.6, 0.0, -0.8], strict=True):
        assert math.isclose(result.score, expected, abs_tol=1e-6)


def test_k_limits_how_many_come_back(corpus):
    results = retriever(corpus).retrieve("anything", k=2)

    assert [r.chunk.title for r in results] == ["Exact", "Near"]


def test_provenance_names_the_strategy_and_ranks_from_one(corpus):
    results = retriever(corpus).retrieve("anything", k=3)

    assert [r.provenance for r in results] == [
        (Provenance("dense", 1),),
        (Provenance("dense", 2),),
        (Provenance("dense", 3),),
    ]


def test_returns_the_chunk_with_its_document_and_location(corpus):
    top = retriever(corpus).retrieve("anything", k=1)[0].chunk

    assert top.title == "Exact"
    assert top.source_path == "exact.md"
    assert top.heading_path == ("Section", "Sub")
    assert top.text == "exact text"
    assert (top.ordinal, top.char_start, top.char_end) == (0, 10, 20)


def test_an_empty_table_returns_nothing(db):
    assert retriever(db).retrieve("anything", k=5) == []


def test_rejects_a_k_below_one(db):
    with pytest.raises(ValueError):
        retriever(db).retrieve("anything", k=0)


@pytest.mark.parametrize(
    ("ef_search", "k", "expected"),
    [
        (40, 5, 40),  # the setting, when it already covers k
        (40, 100, 100),  # raised to k, or the index would cut the results short
        (40, 5000, HNSW_EF_SEARCH_MAX),  # never past what pgvector accepts
    ],
)
def test_sets_ef_search_to_cover_k(db, ef_search, k, expected):
    retriever(db, ef_search=ef_search).retrieve("anything", k=k)

    # The setting is local to a transaction, and the db fixture's transaction is still
    # open, so the value the search ran with is still readable here.
    setting = db.execute("SELECT current_setting('hnsw.ef_search') AS v").fetchone()["v"]
    assert int(setting) == expected


def test_skips_and_warns_about_embeddings_from_another_model(corpus, caplog):
    store(corpus, "Stale", "stale text", plane(1.0, 0.0), model="old-model")
    store(corpus, "Stale2", "stale text", plane(1.0, 0.0), revision="0")

    with caplog.at_level(logging.WARNING, logger="portfolio_bot.retrieval.dense"):
        results = retriever(corpus).retrieve("anything", k=10)

    # Both stale chunks point exactly at the query, so ranking them would put them first.
    assert [r.chunk.title for r in results] == ["Exact", "Near", "Unrelated", "Opposite"]
    [record] = caplog.records
    assert record.skipped == 2
    assert record.models == ["old-model@1", "test-model@0"]


def test_logs_nothing_when_every_embedding_matches(corpus, caplog):
    with caplog.at_level(logging.WARNING, logger="portfolio_bot.retrieval.dense"):
        retriever(corpus).retrieve("anything", k=4)

    assert caplog.records == []


def test_satisfies_the_retrieval_strategy_protocol(db):
    strategy = retriever(db)

    assert isinstance(strategy, RetrievalStrategy)
    assert strategy.name == "dense"
