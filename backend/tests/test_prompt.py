"""The prompt carries the persona, the grounding rules, and the passages, in one shape."""

import re

from portfolio_bot.generation.context import assemble_context
from portfolio_bot.generation.prompt import (
    CONTACT_EMAIL,
    CONTACT_LINKEDIN,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_messages,
)
from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk
from portfolio_bot.settings import REPO_ROOT


def passages():
    chunk = RetrievedChunk(
        1,
        1,
        "education.md",
        "Education",
        ("Degrees and dates",),
        0,
        "I graduated in May 2026.",
        0,
        24,
    )
    return assemble_context([ScoredChunk(chunk, 0.9, (Provenance("dense", 1),))], token_budget=1000)


def test_the_version_is_a_dated_string():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", PROMPT_VERSION)


def test_the_system_prompt_holds_the_persona_and_the_rules():
    text = " ".join(SYSTEM_PROMPT.split())

    assert "close friend of Tae's" in text
    assert "You are not Tae" in text
    assert 'Every "I" in a passage means Tae' in text
    assert "Answer only from the passages" in text
    assert "[1]" in text
    assert CONTACT_EMAIL in text and CONTACT_LINKEDIN in text
    assert 'Never mention "passages"' in text


def test_the_contact_details_match_the_corpus():
    skills = (REPO_ROOT / "content" / "skills.md").read_text()

    assert CONTACT_EMAIL in skills
    assert CONTACT_LINKEDIN in skills


def test_messages_are_the_system_prompt_then_passages_and_question():
    messages = build_messages("  Where did Tae go to school?  ", passages())

    assert [m.role for m in messages] == ["system", "user"]
    assert messages[0].content == SYSTEM_PROMPT
    assert messages[1].content == (
        "Passages:\n\n"
        "[1] Education > Degrees and dates\nI graduated in May 2026.\n\n"
        "Question: Where did Tae go to school?"
    )
