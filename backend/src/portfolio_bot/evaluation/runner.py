"""Run the evaluation set through a strategy and collect per-question and average scores."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any

import psycopg

from portfolio_bot.evaluation.metrics import precision_at_k, recall_at_k, reciprocal_rank
from portfolio_bot.evaluation.questions import EvalQuestion, EvalSetError, Section
from portfolio_bot.retrieval.base import RetrievalStrategy

Connection = psycopg.Connection[dict[str, Any]]


@dataclass(frozen=True)
class QuestionResult:
    question: EvalQuestion
    retrieved: tuple[Section, ...]
    recall: float
    reciprocal_rank: float
    precision: float

    @property
    def first_hit(self) -> int | None:
        """The rank of the first relevant chunk, or None for a miss."""
        return round(1 / self.reciprocal_rank) if self.reciprocal_rank else None


@dataclass(frozen=True)
class EvalReport:
    strategy: str
    k: int
    results: tuple[QuestionResult, ...]

    @property
    def recall(self) -> float:
        return fmean(r.recall for r in self.results)

    @property
    def mrr(self) -> float:
        return fmean(r.reciprocal_rank for r in self.results)

    @property
    def precision(self) -> float:
        return fmean(r.precision for r in self.results)


def known_sections(conn: Connection) -> set[Section]:
    """Every (file, heading path) that at least one stored chunk sits under."""
    rows = conn.execute(
        """
        SELECT DISTINCT d.source_path, c.heading_path
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        """
    ).fetchall()
    return {Section(row["source_path"], tuple(row["heading_path"])) for row in rows}


def check_sections(questions: Sequence[EvalQuestion], known: set[Section]) -> None:
    """Refuse an expected section that covers no stored chunk.

    A typo or a renamed heading would otherwise score as a miss on every run, and look
    like a retrieval failure rather than a mistake in the file.
    """
    problems = [
        f"{q.question!r}: no chunk lies under {str(section)!r}"
        for q in questions
        for section in q.expected
        if not any(section.covers(stored) for stored in known)
    ]
    if problems:
        raise EvalSetError(
            "\n".join([*problems, "Run 'pb eval sections' to list the sections that exist."])
        )


def evaluate(strategy: RetrievalStrategy, questions: Sequence[EvalQuestion], k: int) -> EvalReport:
    """Score `strategy` on every question at cutoff k."""
    if not questions:
        raise EvalSetError("the evaluation set has no questions yet")
    results = []
    for question in questions:
        retrieved = tuple(
            Section(r.chunk.source_path, r.chunk.heading_path)
            for r in strategy.retrieve(question.question, k)
        )[:k]
        results.append(
            QuestionResult(
                question=question,
                retrieved=retrieved,
                recall=recall_at_k(retrieved, question.expected),
                reciprocal_rank=reciprocal_rank(retrieved, question.expected),
                precision=precision_at_k(retrieved, question.expected, k),
            )
        )
    return EvalReport(strategy=strategy.name, k=k, results=tuple(results))
