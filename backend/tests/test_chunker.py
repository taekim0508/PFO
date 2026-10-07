"""The chunker splits at the right places and every chunk points at its own source text.

Sizes here are tiny so boundaries are easy to see. The real values come from settings.
"""

import pytest

from portfolio_bot.ingest.chunker import chunk_document


def chunk(text, size=1000, overlap=0):
    return chunk_document(text, 0, size, overlap)


def texts(chunks):
    return [c.text for c in chunks]


def assert_spans_are_true(text, chunks, size):
    for c in chunks:
        assert c.text == text[c.char_start : c.char_end]
        assert len(c.text) <= size
        assert c.text == c.text.strip()
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_a_document_shorter_than_one_chunk_is_one_chunk():
    text = "Just a sentence.\n"
    chunks = chunk(text)

    assert texts(chunks) == ["Just a sentence."]
    assert chunks[0].heading_path == ()
    assert (chunks[0].char_start, chunks[0].char_end) == (0, 16)


def test_no_headings_at_all_splits_at_blank_lines():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird one.\n"
    chunks = chunk(text, size=30)

    assert texts(chunks) == ["First paragraph here.", "Second paragraph here.", "Third one."]
    assert_spans_are_true(text, chunks, 30)


def test_small_paragraphs_are_packed_together_up_to_the_limit():
    text = "Aa.\n\nBb.\n\nCc.\n\nDd.\n"
    chunks = chunk(text, size=10)

    assert texts(chunks) == ["Aa.\n\nBb.", "Cc.\n\nDd."]


def test_each_heading_starts_a_new_chunk_with_its_path():
    text = (
        "# Title\n\nIntro.\n\n"
        "## Alpha\n\nAlpha body.\n\n"
        "### Deeper\n\nDeep body.\n\n"
        "## Beta\n\nBeta body.\n"
    )
    chunks = chunk(text)

    assert texts(chunks) == [
        "# Title\n\nIntro.",
        "## Alpha\n\nAlpha body.",
        "### Deeper\n\nDeep body.",
        "## Beta\n\nBeta body.",
    ]
    assert [c.heading_path for c in chunks] == [
        ("Title",),
        ("Title", "Alpha"),
        ("Title", "Alpha", "Deeper"),
        ("Title", "Beta"),
    ]


def test_a_heading_with_nothing_under_it_is_not_a_chunk_but_stays_in_the_path():
    text = "## Parent\n\n### Child\n\nChild body.\n"
    chunks = chunk(text)

    assert texts(chunks) == ["### Child\n\nChild body."]
    assert chunks[0].heading_path == ("Parent", "Child")


def test_a_paragraph_longer_than_the_limit_splits_at_sentences():
    text = "One two three. Four five six. Seven eight nine.\n"
    chunks = chunk(text, size=20)

    assert texts(chunks) == ["One two three.", "Four five six.", "Seven eight nine."]
    assert_spans_are_true(text, chunks, 20)


def test_text_with_no_sentence_ends_gets_a_hard_cut_at_a_space():
    text = "alpha beta gamma delta epsilon zeta"
    chunks = chunk(text, size=12)

    assert texts(chunks) == ["alpha beta", "gamma delta", "epsilon zeta"]
    assert_spans_are_true(text, chunks, 12)


def test_a_word_longer_than_the_limit_is_cut_mid_word():
    text = "abcdefghijklmnop"
    assert texts(chunk(text, size=5)) == ["abcde", "fghij", "klmno", "p"]


def test_a_code_fence_is_not_split_at_its_blank_lines_or_sentences():
    fence = "```\nx = 1.\n\ny = 2. z = 3.\n```"
    text = f"Before.\n\n{fence}\n\nAfter.\n"
    chunks = chunk(text, size=len(fence))

    assert fence in texts(chunks)
    assert_spans_are_true(text, chunks, len(fence))


def test_a_heading_inside_a_code_fence_is_not_a_heading():
    text = "## Real\n\n```\n## not a heading\n```\n"
    chunks = chunk(text)

    assert len(chunks) == 1
    assert chunks[0].heading_path == ("Real",)


def test_overlap_repeats_the_end_of_the_previous_chunk_from_a_word_boundary():
    text = "One two three. Four five six. Seven eight nine.\n"
    chunks = chunk(text, size=24, overlap=8)

    assert texts(chunks) == ["One two three.", "three. Four five six.", "six. Seven eight nine."]
    assert_spans_are_true(text, chunks, 24)


def test_overlap_never_crosses_a_heading():
    text = "## A\n\nFirst section text.\n\n## B\n\nSecond section text.\n"
    chunks = chunk(text, size=30, overlap=10)

    assert texts(chunks) == ["## A\n\nFirst section text.", "## B\n\nSecond section text."]


def test_overlap_is_dropped_when_it_would_push_a_chunk_over_the_limit():
    text = "Aaaa aaaa aaaa. Bbbb bbbb bbbb.\n"
    chunks = chunk(text, size=15, overlap=6)

    assert texts(chunks) == ["Aaaa aaaa aaaa.", "Bbbb bbbb bbbb."]


def test_offsets_are_into_the_whole_file_when_the_body_starts_later():
    text = "---\ntitle: T\n---\n\nHello there.\n"
    body_start = text.index("\n\nHello")
    chunks = chunk_document(text, body_start, 1000, 0)

    assert chunks[0].text == "Hello there."
    assert text[chunks[0].char_start : chunks[0].char_end] == "Hello there."


def test_an_empty_body_has_no_chunks():
    assert chunk("   \n\n  ") == []


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_rejects_impossible_settings(size, overlap):
    with pytest.raises(ValueError):
        chunk("text", size=size, overlap=overlap)
