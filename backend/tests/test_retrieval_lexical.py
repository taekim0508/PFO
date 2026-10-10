"""Lexical retrieval ranks chunks by the words they share with the question.

Every chunk here is inserted without an embedding, so every passing test also shows that
lexical search does not depend on one.
"""

import pytest

from portfolio_bot.retrieval.base import Provenance, RetrievalStrategy
from portfolio_bot.retrieval.lexical import SEARCH_SQL, LexicalRetriever

pytestmark = pytest.mark.database


def store(db, title, text, *, heading_path=()):
    """Insert one document with one chunk and no embedding. Returns the chunk id."""
    document_id = db.execute(
        "INSERT INTO documents (source_path, title, content_hash) VALUES (%s, %s, 'h') "
        "RETURNING id",
        (f"{title.lower()}.md", title),
    ).fetchone()["id"]
    return db.execute(
        """
        INSERT INTO chunks
            (document_id, ordinal, text, token_count, heading_path, char_start, char_end)
        VALUES (%s, 0, %s, 1, %s, 10, %s)
        RETURNING id
        """,
        (document_id, text, list(heading_path), 10 + len(text)),
    ).fetchone()["id"]


@pytest.fixture
def corpus(db):
    # Inserted with the weakest match first, so a correct ranking cannot come from
    # insertion order or chunk id.
    store(db, "One", "A result appears here.")
    store(db, "Unrelated", "Nothing relevant at all.")
    store(db, "Three", "The chatbot can rank every result.", heading_path=("Section",))
    return db


def titles(results):
    return [r.chunk.title for r in results]


def test_more_shared_words_rank_higher_and_non_matches_are_left_out(corpus):
    # The question reduces to chatbot, rank, result. Three shares all of them, One shares
    # only result, Unrelated shares none.
    results = LexicalRetriever(corpus).retrieve("How does the chatbot rank results?", k=5)

    assert titles(results) == ["Three", "One"]
    assert results[0].score > results[1].score > 0


def test_a_word_found_nowhere_does_not_stop_the_others_matching(corpus):
    results = LexicalRetriever(corpus).retrieve("chatbot zebra", k=5)

    assert titles(results) == ["Three"]


def test_matches_different_forms_of_the_same_word(db):
    store(db, "Chunker", "The chunker splits text at headings.")

    # Both "splitting" and "splits" reduce to the stem split.
    assert titles(LexicalRetriever(db).retrieve("splitting", k=5)) == ["Chunker"]


def test_a_question_of_only_common_words_returns_nothing(corpus):
    assert LexicalRetriever(corpus).retrieve("where is it?", k=5) == []


def test_no_match_returns_nothing(corpus):
    assert LexicalRetriever(corpus).retrieve("zebra", k=5) == []


def test_k_limits_how_many_come_back(corpus):
    assert titles(LexicalRetriever(corpus).retrieve("chatbot rank result", k=1)) == ["Three"]


def test_ties_come_back_in_chunk_id_order(db):
    first = store(db, "First", "A result.")
    second = store(db, "Second", "A result.")

    results = LexicalRetriever(db).retrieve("result", k=5)

    assert results[0].score == results[1].score
    assert [r.chunk.chunk_id for r in results] == [first, second]


def test_provenance_names_the_strategy_and_ranks_from_one(corpus):
    results = LexicalRetriever(corpus).retrieve("chatbot result", k=5)

    assert [r.provenance for r in results] == [
        (Provenance("lexical", 1),),
        (Provenance("lexical", 2),),
    ]


def test_returns_the_chunk_with_its_document_and_location(corpus):
    top = LexicalRetriever(corpus).retrieve("chatbot", k=1)[0].chunk

    assert top.title == "Three"
    assert top.source_path == "three.md"
    assert top.heading_path == ("Section",)
    assert top.text == "The chatbot can rank every result."
    assert (top.ordinal, top.char_start, top.char_end) == (0, 10, 44)


@pytest.mark.parametrize("query", ["result & chatbot", "result | !chatbot", "'result' (chatbot"])
def test_query_syntax_characters_are_read_as_text(corpus, query):
    # Each would be an operator or a syntax error in a raw tsquery. Here they are ignored
    # and the words still match.
    assert titles(LexicalRetriever(corpus).retrieve(query, k=5)) == ["Three", "One"]


def test_rejects_a_k_below_one(db):
    with pytest.raises(ValueError):
        LexicalRetriever(db).retrieve("result", k=0)


def test_the_search_uses_the_full_text_index(corpus):
    # With a handful of rows the planner rightly prefers reading the table, so sequential
    # scans are switched off to ask the real question: can this exact query use the index.
    # A query spelling the expression differently from the index would fail here.
    corpus.execute("SET LOCAL enable_seqscan = off")
    plan = "\n".join(
        row["QUERY PLAN"]
        for row in corpus.execute(
            "EXPLAIN " + SEARCH_SQL, {"query": "chatbot rank", "k": 5}
        ).fetchall()
    )

    assert "chunks_text_fts" in plan


def test_satisfies_the_retrieval_strategy_protocol(db):
    strategy = LexicalRetriever(db)

    assert isinstance(strategy, RetrievalStrategy)
    assert strategy.name == "lexical"
