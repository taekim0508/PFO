"""The ask pipeline: sources first, then the answer, then what it cited, or a fixed reply.

Retrieval here is a scripted strategy, so each test controls exactly what was "found" and
how confidently. The model is the fake client, so the test also sees what it was sent.
"""

import pytest

from portfolio_bot.generation.ask import (
    NO_CONTEXT_ANSWER,
    AnswerDone,
    Sources,
    ask,
    citations,
)
from portfolio_bot.generation.client import (
    FakeModelClient,
    ModelUnavailableError,
    StreamDone,
    TextDelta,
)
from portfolio_bot.generation.prompt import PROMPT_VERSION, build_messages
from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk


def found(chunk_id, score, text="I graduated from Vanderbilt in May 2026."):
    chunk = RetrievedChunk(
        chunk_id, 1, "education.md", "Education", ("Degrees and dates",), 0, text, 0, len(text)
    )
    return ScoredChunk(chunk, score, (Provenance("dense", chunk_id),))


class ScriptedStrategy:
    def __init__(self, results, name="dense"):
        self.name = name
        self._results = results
        self.calls = []

    def retrieve(self, query, k):
        self.calls.append((query, k))
        return self._results[:k]


async def run(question, strategy, client, *, floor=0.5, k=5):
    return [
        event
        async for event in ask(
            question,
            strategy=strategy,
            client=client,
            k=k,
            token_budget=2500,
            relevance_floor=floor,
            temperature=0.2,
            max_tokens=300,
        )
    ]


# Citations


@pytest.mark.parametrize(
    ("text", "valid", "invalid"),
    [
        ("No citations.", (), ()),
        ("A [1]. B [2][3]. C [1].", (1, 2, 3), ()),
        ("A [2]. B [9].", (2,), (9,)),
        ("A [0] and [10].", (), (0, 10)),
        ("Not a citation: [x] or [ 1 ].", (), ()),
    ],
)
def test_citations_are_split_into_real_passages_and_invented_ones(text, valid, invalid):
    assert citations(text, labels=[1, 2, 3]) == (valid, invalid)


# Answering


async def test_sources_come_first_then_the_answer_then_done():
    client = FakeModelClient(["Tae graduated from Vanderbilt in May 2026 [1]."])

    events = await run("Where did Tae go to school?", ScriptedStrategy([found(1, 0.8)]), client)

    assert isinstance(events[0], Sources)
    assert [p.label for p in events[0].passages] == [1]
    assert events[0].strategy == "dense"
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(deltas) == "Tae graduated from Vanderbilt in May 2026 [1]."
    done = events[-1]
    assert isinstance(done, AnswerDone)
    assert done.no_context is False
    assert done.cited == (1,)
    assert done.invalid_citations == ()
    assert done.finish_reason == "stop"
    assert done.model == "fake"
    assert done.prompt_version == PROMPT_VERSION
    assert done.first_text_seconds is not None
    assert done.total_seconds >= done.retrieval_seconds


async def test_the_model_gets_the_built_messages_and_the_answer_settings():
    strategy = ScriptedStrategy([found(1, 0.8), found(2, 0.7)])
    client = FakeModelClient(["Answer."])

    events = await run("Where did Tae go to school?", strategy, client, k=2)

    messages, options = client.calls[0]
    assert list(messages) == build_messages("Where did Tae go to school?", events[0].passages)
    assert options == {"temperature": 0.2, "max_tokens": 300}
    assert strategy.calls == [("Where did Tae go to school?", 2)]


async def test_an_invented_citation_is_reported():
    client = FakeModelClient(["He studied there [1][4]."])

    events = await run("q", ScriptedStrategy([found(1, 0.8)]), client)

    assert events[-1].cited == (1,)
    assert events[-1].invalid_citations == (4,)


# The no-context path


async def test_nothing_retrieved_answers_with_the_fixed_reply_and_never_calls_the_model():
    client = FakeModelClient()

    events = await run("Anything?", ScriptedStrategy([]), client)

    assert events[0] == Sources(strategy="dense", passages=())
    assert events[1] == TextDelta(NO_CONTEXT_ANSWER)
    assert events[-1].no_context is True
    assert events[-1].model is None
    assert client.calls == []


async def test_a_dense_match_below_the_floor_takes_the_no_context_path():
    client = FakeModelClient()

    events = await run("Capital of France?", ScriptedStrategy([found(1, 0.49)]), client, floor=0.5)

    assert events[-1].no_context is True
    assert client.calls == []


async def test_a_dense_match_at_the_floor_is_answered():
    client = FakeModelClient()

    events = await run("q", ScriptedStrategy([found(1, 0.5)]), client, floor=0.5)

    assert events[-1].no_context is False
    assert len(client.calls) == 1


async def test_the_floor_applies_only_to_dense_scores():
    # Lexical and fused scores are on other scales; 0.1 is a normal lexical score.
    client = FakeModelClient()

    events = await run("q", ScriptedStrategy([found(1, 0.1)], name="lexical"), client, floor=0.5)

    assert events[-1].no_context is False


def test_the_fixed_reply_names_both_ways_to_reach_tae():
    assert "taekim0508@gmail.com" in NO_CONTEXT_ANSWER
    assert "linkedin.com/in/kimtae03" in NO_CONTEXT_ANSWER


# Failures


class BreakingClient(FakeModelClient):
    async def stream(self, messages, *, temperature=None, max_tokens=None):
        yield TextDelta("Tae ")
        raise ModelUnavailableError("the reply stream broke partway")


async def test_a_model_failure_surfaces_after_what_was_already_sent():
    received = []

    with pytest.raises(ModelUnavailableError):
        async for event in ask(
            "q",
            strategy=ScriptedStrategy([found(1, 0.8)]),
            client=BreakingClient(),
            k=5,
            token_budget=2500,
            relevance_floor=0.5,
        ):
            received.append(event)

    assert isinstance(received[0], Sources)
    assert received[1] == TextDelta("Tae ")


async def test_a_stream_without_a_done_event_still_finishes():
    class NoDone(FakeModelClient):
        async def stream(self, messages, *, temperature=None, max_tokens=None):
            yield TextDelta("Answer [1].")

    events = await run("q", ScriptedStrategy([found(1, 0.8)]), NoDone())

    assert events[-1].cited == (1,)
    assert events[-1].finish_reason is None


def test_stream_done_is_not_an_answer_event():
    # AnswerDone is the pipeline's; StreamDone stays inside it.
    assert not issubclass(StreamDone, AnswerDone)
