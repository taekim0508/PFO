"""The shapes the API accepts and sends.

A chat answer arrives as Server-Sent Events, one named event per step, each carrying one of
the payloads below as JSON:

- `sources`, once, first: the numbered passages the answer may cite.
- `delta`, many: the next piece of the answer's text.
- `done`, once, last: how it ended, what it cited, timings in milliseconds.
- `error`, at most once, in place of `done`: a code and a sentence safe to show a visitor.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from portfolio_bot.generation.ask import AnswerDone, Sources
from portfolio_bot.settings import get_settings

StrategyName = Literal["dense", "lexical", "hybrid"]


class ChatRequest(BaseModel):
    """One question. `strategy` and `k` are for the inspector and experiments."""

    question: str
    strategy: StrategyName | None = None
    k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def question_is_present_and_short_enough(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("the question is empty")
        limit = get_settings().max_question_chars
        if len(value) > limit:
            raise ValueError(f"the question is longer than {limit} characters")
        return value


class ProvenanceOut(BaseModel):
    strategy: str
    rank: int


class PassageOut(BaseModel):
    """One passage the answer may cite, with what the inspector shows about it."""

    label: int
    title: str
    heading_path: list[str]
    source_path: str
    location: str
    text: str
    score: float
    provenance: list[ProvenanceOut]


class SourcesEvent(BaseModel):
    strategy: str
    passages: list[PassageOut]

    @classmethod
    def of(cls, sources: Sources) -> SourcesEvent:
        return cls(
            strategy=sources.strategy,
            passages=[
                PassageOut(
                    label=p.label,
                    title=p.result.chunk.title,
                    heading_path=list(p.result.chunk.heading_path),
                    source_path=p.result.chunk.source_path,
                    location=p.location,
                    text=p.result.chunk.text,
                    score=p.result.score,
                    provenance=[
                        ProvenanceOut(strategy=v.strategy, rank=v.rank) for v in p.result.provenance
                    ],
                )
                for p in sources.passages
            ],
        )


class DeltaEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    no_context: bool
    model: str | None
    finish_reason: str | None
    prompt_version: str
    cited: list[int]
    invalid_citations: list[int]
    retrieval_ms: int
    first_text_ms: int | None
    total_ms: int

    @classmethod
    def of(cls, done: AnswerDone) -> DoneEvent:
        return cls(
            no_context=done.no_context,
            model=done.model,
            finish_reason=done.finish_reason,
            prompt_version=done.prompt_version,
            cited=list(done.cited),
            invalid_citations=list(done.invalid_citations),
            retrieval_ms=round(done.retrieval_seconds * 1000),
            first_text_ms=(
                round(done.first_text_seconds * 1000)
                if done.first_text_seconds is not None
                else None
            ),
            total_ms=round(done.total_seconds * 1000),
        )


ErrorCode = Literal[
    "model_unavailable", "model_error", "database_unavailable", "timeout", "internal"
]


class ErrorEvent(BaseModel):
    code: ErrorCode
    message: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    git_sha: str
    model: str
    prompt_version: str
