"""Scores for one question's results. Averaging across questions happens in the runner.

Each function takes the sections of the retrieved chunks, best first and already cut to k,
and the sections the question expects. A retrieved chunk is relevant when an expected
section covers it. Several chunks can come from one expected section, which is why recall
counts expected sections found while precision counts relevant chunks returned.
"""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_bot.evaluation.questions import Section


def _relevant(retrieved: Section, expected: Sequence[Section]) -> bool:
    return any(section.covers(retrieved) for section in expected)


def recall_at_k(retrieved: Sequence[Section], expected: Sequence[Section]) -> float:
    """Share of the expected sections that at least one retrieved chunk came from."""
    found = sum(1 for section in expected if any(section.covers(r) for r in retrieved))
    return found / len(expected)


def reciprocal_rank(retrieved: Sequence[Section], expected: Sequence[Section]) -> float:
    """1 / the rank of the first relevant chunk, or 0 if none was retrieved."""
    for rank, section in enumerate(retrieved, start=1):
        if _relevant(section, expected):
            return 1.0 / rank
    return 0.0


def precision_at_k(retrieved: Sequence[Section], expected: Sequence[Section], k: int) -> float:
    """Share of the k slots holding a relevant chunk.

    Divided by k rather than by how many came back, so a strategy that returns two chunks
    for k=5 is not credited with perfect precision for getting both right.
    """
    return sum(1 for section in retrieved if _relevant(section, expected)) / k
