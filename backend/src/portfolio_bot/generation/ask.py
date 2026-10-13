"""Answering a question: retrieve, decide whether there is anything to answer from, generate.

One pipeline serves `pb ask` and, later, the chat API, as a stream of events:

1. `Sources`: the numbered passages the answer may cite, sent before any text, so a reader
   can see what was found while the answer is still being written. Empty on the
   no-context path.
2. `TextDelta`: the answer, piece by piece.
3. `AnswerDone`: how it ended, which passages the answer actually cited, the prompt
   version, and timings.

The no-context path: when retrieval finds nothing, or nothing it is confident about, the
model is never called. It would only be asked to answer from passages that do not answer
the question, which is the situation most likely to produce an invented answer. A fixed
message goes out instead. The confidence test is a floor on the best dense similarity,
measured against real and off-topic questions (see Findings). Other strategies' scores are
on other scales, so for them only "nothing retrieved" takes this path, and the prompt's
own refusal rule is the safety net.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from portfolio_bot.generation.client import ModelClient, StreamDone, TextDelta
from portfolio_bot.generation.context import ContextPassage, assemble_context
from portfolio_bot.generation.prompt import (
    CONTACT_EMAIL,
    CONTACT_LINKEDIN,
    PROMPT_VERSION,
    build_messages,
)
from portfolio_bot.retrieval.base import RetrievalStrategy

NO_CONTEXT_ANSWER = (
    "Tae hasn't written about anything that matches that question, so I'd rather not guess. "
    f"You can ask him directly at {CONTACT_EMAIL} or on LinkedIn ({CONTACT_LINKEDIN})."
)

_CITATION = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Sources:
    """The passages the answer may cite, and the strategy that found them."""

    strategy: str
    passages: tuple[ContextPassage, ...]


@dataclass(frozen=True)
class AnswerDone:
    """The last event of an answer.

    `cited` holds the passage numbers the answer cites that exist; `invalid_citations`
    holds numbers it cites that match no passage, which is a model error worth counting.
    Timings are in seconds from the start of the question; `first_text` is None when no
    text was produced.
    """

    no_context: bool
    model: str | None
    finish_reason: str | None
    prompt_version: str
    cited: tuple[int, ...]
    invalid_citations: tuple[int, ...]
    retrieval_seconds: float
    first_text_seconds: float | None
    total_seconds: float


AskEvent = Sources | TextDelta | AnswerDone


def citations(text: str, labels: Sequence[int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The passage numbers `text` cites, split into ones in `labels` and ones not.

    Each list is sorted and without repeats.
    """
    found = {int(number) for number in _CITATION.findall(text)}
    valid = set(labels)
    return tuple(sorted(found & valid)), tuple(sorted(found - valid))


async def ask(
    question: str,
    *,
    strategy: RetrievalStrategy,
    client: ModelClient,
    k: int,
    token_budget: int,
    relevance_floor: float,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[AskEvent, None]:
    """Answer `question` as a stream of events: `Sources`, `TextDelta`s, `AnswerDone`.

    Retrieval is blocking database and model work, so it runs on a worker thread and the
    event loop stays free for other requests. Model errors propagate after whatever was
    already yielded; the caller decides how to report them.
    """
    started = time.perf_counter()
    results = await asyncio.to_thread(strategy.retrieve, question, k)
    retrieval_seconds = time.perf_counter() - started

    if _nothing_to_answer_from(strategy.name, [r.score for r in results], relevance_floor):
        yield Sources(strategy=strategy.name, passages=())
        yield TextDelta(NO_CONTEXT_ANSWER)
        yield AnswerDone(
            no_context=True,
            model=None,
            finish_reason=None,
            prompt_version=PROMPT_VERSION,
            cited=(),
            invalid_citations=(),
            retrieval_seconds=retrieval_seconds,
            first_text_seconds=time.perf_counter() - started,
            total_seconds=time.perf_counter() - started,
        )
        return

    passages = assemble_context(results, token_budget=token_budget)
    yield Sources(strategy=strategy.name, passages=tuple(passages))

    pieces: list[str] = []
    first_text: float | None = None
    done: StreamDone | None = None
    async for event in client.stream(
        build_messages(question, passages), temperature=temperature, max_tokens=max_tokens
    ):
        if isinstance(event, TextDelta):
            if first_text is None:
                first_text = time.perf_counter() - started
            pieces.append(event.text)
            yield event
        else:
            done = event

    cited, invalid = citations("".join(pieces), [p.label for p in passages])
    yield AnswerDone(
        no_context=False,
        model=done.model if done else client.model_name,
        finish_reason=done.finish_reason if done else None,
        prompt_version=PROMPT_VERSION,
        cited=cited,
        invalid_citations=invalid,
        retrieval_seconds=retrieval_seconds,
        first_text_seconds=first_text,
        total_seconds=time.perf_counter() - started,
    )


def _nothing_to_answer_from(strategy: str, scores: Sequence[float], floor: float) -> bool:
    if not scores:
        return True
    return strategy == "dense" and max(scores) < floor
