"""Retrieved chunks become numbered passages, in order, without repeats, within budget."""

from portfolio_bot.generation.context import (
    ContextPassage,
    assemble_context,
    estimate_tokens,
    render_context,
)
from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk


def result(chunk_id, text="Some text.", *, title="Education", headings=("Degrees",), score=0.5):
    chunk = RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        source_path="education.md",
        title=title,
        heading_path=headings,
        ordinal=chunk_id,
        text=text,
        char_start=0,
        char_end=len(text),
    )
    return ScoredChunk(chunk=chunk, score=score, provenance=(Provenance("dense", chunk_id),))


def test_estimates_a_quarter_of_the_characters_rounded_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_passages_are_numbered_from_one_in_retrieval_order():
    passages = assemble_context([result(7), result(3), result(9)], token_budget=1000)

    assert [p.label for p in passages] == [1, 2, 3]
    assert [p.result.chunk.chunk_id for p in passages] == [7, 3, 9]


def test_a_repeated_chunk_is_kept_once_in_its_first_place():
    passages = assemble_context([result(7), result(3), result(7)], token_budget=1000)

    assert [p.result.chunk.chunk_id for p in passages] == [7, 3]


def test_whole_passages_are_dropped_from_the_bottom_to_fit_the_budget():
    # Each renders as "[n] Education > Degrees\n" plus 80 characters: 103 characters, 26 tokens.
    results = [result(i, "x" * 80) for i in range(1, 6)]
    assert estimate_tokens(ContextPassage(1, results[0]).render()) == 26

    passages = assemble_context(results, token_budget=60)

    assert [p.label for p in passages] == [1, 2]
    assert all(p.result.chunk.text == "x" * 80 for p in passages)  # none cut short


def test_the_best_passage_is_kept_even_when_it_alone_is_over_budget():
    passages = assemble_context([result(1, "x" * 400), result(2)], token_budget=10)

    assert [p.label for p in passages] == [1]


def test_nothing_retrieved_means_no_passages():
    assert assemble_context([], token_budget=1000) == []


def test_renders_each_passage_with_its_number_location_and_text():
    passages = assemble_context(
        [
            result(1, "  I graduated in May 2026.\n", headings=("Degrees and dates",)),
            result(2, "Data Structures.", title="Education", headings=()),
        ],
        token_budget=1000,
    )

    assert render_context(passages) == (
        "[1] Education > Degrees and dates\nI graduated in May 2026.\n\n"
        "[2] Education\nData Structures."
    )
