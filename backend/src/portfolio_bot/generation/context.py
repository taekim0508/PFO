"""Turning retrieved chunks into the numbered passages a model reads and cites.

The model only ever sees what this block contains, so it decides what the answer can say.
Each passage gets a number the model cites as [1], [2], and so on, and that number is how
an answer's citation is traced back to a real file and section. Numbers follow retrieval
order and are fixed before any truncation, so passage 1 is always the best match.

The size limit is in tokens because that is what a model's context window counts. Tokens
are estimated as a quarter of the characters, which is close for English prose and means
this module needs no tokenizer for whichever model happens to be configured.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from portfolio_bot.retrieval.base import ScoredChunk

# Roughly how many characters one token covers in English text.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ContextPassage:
    """One retrieved chunk as the model sees it, with the number it is cited by."""

    label: int
    result: ScoredChunk

    @property
    def location(self) -> str:
        """`Title > Heading > Subheading`, the same form `pb search` prints."""
        chunk = self.result.chunk
        return " > ".join([chunk.title, *chunk.heading_path])

    def render(self) -> str:
        return f"[{self.label}] {self.location}\n{self.result.chunk.text.strip()}"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def assemble_context(results: Sequence[ScoredChunk], *, token_budget: int) -> list[ContextPassage]:
    """The passages to show the model: retrieval order, no repeats, within the budget.

    A chunk that appears twice (two strategies can hand back the same one) is kept once,
    in its first position. Passages are then added best first until the next one would
    pass `token_budget`; whole passages are dropped from the bottom and none is ever cut
    short. The first passage is always kept, even alone over budget, because an answer
    with no context at all is the no-context path's decision, not this function's.
    """
    seen: set[int] = set()
    unique = []
    for result in results:
        if result.chunk.chunk_id not in seen:
            seen.add(result.chunk.chunk_id)
            unique.append(result)

    passages: list[ContextPassage] = []
    used = 0
    for label, result in enumerate(unique, start=1):
        passage = ContextPassage(label=label, result=result)
        cost = estimate_tokens(passage.render())
        if passages and used + cost > token_budget:
            break
        passages.append(passage)
        used += cost
    return passages


def render_context(passages: Sequence[ContextPassage]) -> str:
    """The passages as one block of text, separated by blank lines."""
    return "\n\n".join(passage.render() for passage in passages)
