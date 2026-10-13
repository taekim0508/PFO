"""The HTTP API, end to end in process: real Postgres, fake embedder, fake model.

Each test builds the app with fakes, runs its startup and shutdown, and talks to it over
httpx without a network. Answers arrive as Server-Sent Events, parsed here into
(event, payload) pairs so assertions read as the sequence a browser would see.
"""

import asyncio
import json

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from portfolio_bot.api.app import ERROR_MESSAGES, create_app
from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.generation.ask import NO_CONTEXT_ANSWER
from portfolio_bot.generation.client import FakeModelClient, ModelUnavailableError, TextDelta
from portfolio_bot.generation.prompt import PROMPT_VERSION
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.ingest.pipeline import ingest
from portfolio_bot.settings import get_settings

pytestmark = pytest.mark.database

DOCUMENT = (
    "---\ntitle: Education\n---\n\n## Degrees and dates\n\n"
    "I graduated from Vanderbilt University in May 2026.\n"
)
REPLY = "Tae graduated from Vanderbilt in May 2026 [1]."


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def corpus(empty_database, monkeypatch, tmp_path):
    run_migrations(empty_database)
    (tmp_path / "education.md").write_text(DOCUMENT)
    with psycopg.connect(empty_database, row_factory=dict_row) as conn:
        ingest(conn, tmp_path, FakeEmbedder(), chunk_size=1000, chunk_overlap=0)
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()
    return empty_database


class Api:
    """An app with fakes, started, and an httpx client pointed at it."""

    def __init__(self, client=None, clock=None):
        self.model = client or FakeModelClient([REPLY])
        self.clock = clock or Clock()
        self.app = create_app(
            get_settings(), embedder=FakeEmbedder(), client=self.model, clock=self.clock
        )

    async def __aenter__(self):
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        transport = httpx.ASGITransport(app=self.app)
        self.http = httpx.AsyncClient(transport=transport, base_url="http://test")
        return self

    async def __aexit__(self, *exc):
        await self.http.aclose()
        await self._lifespan.__aexit__(*exc)

    async def chat(self, **body):
        return await self.http.post("/api/chat", json=body)


def events(response):
    """[(event name, payload)] from an SSE body."""
    parsed = []
    for frame in response.text.split("\n\n"):
        if not frame.strip():
            continue
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


# Health


async def test_health_reports_the_database_the_commit_and_the_model(corpus):
    async with Api() as api:
        response = await api.http.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["git_sha"]
    assert body["model"] == get_settings().model_name
    assert body["prompt_version"] == PROMPT_VERSION


async def test_health_is_degraded_with_503_when_the_database_does_not_answer(corpus, monkeypatch):
    monkeypatch.setattr("portfolio_bot.api.app._database_answers", lambda: False)

    async with Api() as api:
        response = await api.http.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


# Chat


async def test_streams_sources_then_deltas_then_done(corpus):
    async with Api() as api:
        response = await api.chat(
            question="When did he graduate from Vanderbilt?", strategy="lexical"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    sequence = events(response)
    names = [name for name, _ in sequence]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"delta"}

    sources = sequence[0][1]
    assert sources["strategy"] == "lexical"
    [passage] = sources["passages"]
    assert passage["label"] == 1
    assert passage["location"] == "Education > Degrees and dates"
    assert passage["source_path"] == "education.md"
    assert "I graduated from Vanderbilt" in passage["text"]
    assert passage["provenance"] == [{"strategy": "lexical", "rank": 1}]

    assert "".join(payload["text"] for name, payload in sequence if name == "delta") == REPLY

    done = sequence[-1][1]
    assert done["no_context"] is False
    assert done["cited"] == [1]
    assert done["invalid_citations"] == []
    assert done["prompt_version"] == PROMPT_VERSION
    assert isinstance(done["total_ms"], int)


async def test_the_default_strategy_and_floor_give_the_fixed_reply_without_the_model(corpus):
    # The fake embedder's vectors are unrelated, so dense similarity is far under the floor.
    async with Api() as api:
        response = await api.chat(question="What is the capital of France?")

    sequence = events(response)
    assert sequence[0] == ("sources", {"strategy": "dense", "passages": []})
    assert sequence[1] == ("delta", {"text": NO_CONTEXT_ANSWER})
    assert sequence[-1][1]["no_context"] is True
    assert api.model.calls == []


# Input


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"question": "   "}, "the question is empty"),
        ({"question": "x" * 501}, "longer than 500 characters"),
        ({"question": "q", "strategy": "telepathy"}, None),
        ({"question": "q", "k": 0}, None),
        ({}, None),
    ],
)
async def test_bad_input_is_a_422_with_a_readable_message(corpus, body, message):
    async with Api() as api:
        response = await api.http.post("/api/chat", json=body)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    if message:
        assert message in error["message"]


async def test_a_question_at_the_limit_is_accepted(corpus):
    async with Api() as api:
        response = await api.chat(question="x" * 500)

    assert response.status_code == 200


# Rate limit


async def test_the_minute_limit_answers_429_with_retry_after(corpus, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()

    async with Api() as api:
        first = await api.chat(question="q1")
        second = await api.chat(question="q2")
        third = await api.chat(question="q3")
        api.clock.now += 61
        fourth = await api.chat(question="q4")

    assert [r.status_code for r in (first, second, third, fourth)] == [200, 200, 429, 200]
    assert third.json()["error"]["code"] == "rate_limited"
    assert int(third.headers["retry-after"]) == 60


async def test_the_day_limit_holds_across_quiet_minutes(corpus, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_DAY", "2")
    get_settings.cache_clear()

    async with Api() as api:
        statuses = []
        for _ in range(3):
            statuses.append((await api.chat(question="q")).status_code)
            api.clock.now += 300

    assert statuses == [200, 200, 429]


# Failures become one error event, never a trace


class Unavailable(FakeModelClient):
    async def stream(self, messages, *, temperature=None, max_tokens=None):
        yield TextDelta("Tae ")
        raise ModelUnavailableError("could not reach http://internal-host:11434")


class Broken(FakeModelClient):
    async def stream(self, messages, *, temperature=None, max_tokens=None):
        raise RuntimeError("secret detail: postgresql://user:pw@host/db")
        yield TextDelta("")


class Slow(FakeModelClient):
    async def stream(self, messages, *, temperature=None, max_tokens=None):
        await asyncio.sleep(5)
        yield TextDelta("too late")


@pytest.mark.parametrize(
    ("client", "code"),
    [(Unavailable(), "model_unavailable"), (Broken(), "internal")],
)
async def test_a_failure_ends_the_stream_with_an_error_event(corpus, client, code):
    async with Api(client=client) as api:
        response = await api.chat(question="Vanderbilt?", strategy="lexical")

    sequence = events(response)
    assert sequence[0][0] == "sources"
    assert sequence[-1] == ("error", {"code": code, "message": ERROR_MESSAGES[code]})
    assert "done" not in [name for name, _ in sequence]
    assert "internal-host" not in response.text
    assert "postgresql://" not in response.text


async def test_an_answer_past_the_deadline_ends_with_a_timeout_error(corpus, monkeypatch):
    monkeypatch.setenv("CHAT_DEADLINE_SECONDS", "0.2")
    get_settings.cache_clear()

    async with Api(client=Slow()) as api:
        response = await api.chat(question="Vanderbilt?", strategy="lexical")

    assert events(response)[-1] == (
        "error",
        {"code": "timeout", "message": ERROR_MESSAGES["timeout"]},
    )


# CORS


async def test_the_configured_origin_may_call_the_api_and_others_may_not(corpus):
    async with Api() as api:
        allowed = await api.http.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        refused = await api.http.options(
            "/api/chat",
            headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
        )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in refused.headers
