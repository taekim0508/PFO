"""Both embedders return unit vectors of the schema's width; the fake one is deterministic."""

import math

import pytest

from portfolio_bot.ingest.embedder import (
    EMBEDDING_DIMENSION,
    FakeEmbedder,
    SentenceTransformerEmbedder,
)
from portfolio_bot.settings import get_settings


def norm(vector):
    return math.sqrt(sum(value * value for value in vector))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_vectors_are_unit_length_and_the_schema_width():
    vectors = FakeEmbedder().embed(["one", "two"])

    assert [len(v) for v in vectors] == [EMBEDDING_DIMENSION, EMBEDDING_DIMENSION]
    assert all(math.isclose(norm(v), 1.0) for v in vectors)


def test_fake_vectors_are_deterministic_and_differ_by_text():
    embedder = FakeEmbedder()
    first, again, other = embedder.embed(["same", "same", "different"])

    assert first == again
    assert first != other


def test_fake_counts_words_as_tokens():
    assert FakeEmbedder().count_tokens(["a b c", ""]) == [3, 0]


def test_real_embedder_does_not_load_the_model_until_used():
    embedder = SentenceTransformerEmbedder("not/a-real-model", "0", batch_size=8)

    assert embedder.model_name == "not/a-real-model"
    assert embedder.embed([]) == []


@pytest.mark.model
def test_real_model_produces_unit_vectors_that_reflect_meaning():
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model_name, settings.embedding_model_revision, batch_size=8
    )
    query, related, unrelated = embedder.embed(
        [
            "How did Tae speed up a slow database query?",
            "I added composite indexes that cut the listing query from 9.2ms to 0.47ms.",
            "The ambassador program paired students with mentors.",
        ]
    )

    assert len(query) == EMBEDDING_DIMENSION
    assert math.isclose(norm(query), 1.0, rel_tol=1e-5)
    assert dot(query, related) > dot(query, unrelated)
    assert embedder.count_tokens(["hello world"])[0] > 0
