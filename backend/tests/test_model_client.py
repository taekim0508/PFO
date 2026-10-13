"""The model client speaks the chat-completions shape and turns failures into our errors.

Nothing here reaches a real endpoint. The SDK is handed an HTTP client whose transport is
a function in this file, so every test controls exactly what the "server" answers, and the
SDK's sleep between retries is replaced so the waits are recorded instead of spent.
"""

import json

import httpx2
import pytest

from portfolio_bot.generation.client import (
    Completion,
    FakeModelClient,
    Message,
    ModelError,
    ModelRequestError,
    ModelUnavailableError,
    OpenAICompatibleClient,
    StreamDone,
    TextDelta,
    build_model_client,
)
from portfolio_bot.settings import get_settings

BASE_URL = "http://model.test/v1"
HELLO = [Message(role="system", content="Be brief."), Message(role="user", content="Hi")]


def chat_response(text="Hello.", *, finish_reason="stop", model="served-model", usage=True):
    body = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    return httpx2.Response(200, json=body)


class Server:
    """Answers each request with the next scripted response, and keeps every request.

    A script entry that is an exception is raised instead, the way a transport reports a
    refused connection or a timeout.
    """

    def __init__(self, *script):
        self.script = list(script)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def body(self, index=0):
        return json.loads(self.requests[index].content)


def client_for(server, *, base_url=BASE_URL, max_retries=3, reasoning_effort=None):
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    return OpenAICompatibleClient(
        base_url=base_url,
        api_key="secret-key",
        model="test-model",
        timeout=5.0,
        max_retries=max_retries,
        reasoning_effort=reasoning_effort,
        http_client=http,
    )


@pytest.fixture
def waits(monkeypatch):
    """The SDK's sleeps between retries, recorded in seconds instead of slept."""
    recorded = []

    async def record(seconds):
        recorded.append(seconds)

    monkeypatch.setattr("openai._base_client.anyio.sleep", record)
    return recorded


def error(status, body="nope", **headers):
    return httpx2.Response(status, json={"error": {"message": body}}, headers=headers)


# The request


async def test_posts_the_model_and_messages_to_chat_completions_with_the_key():
    server = Server(chat_response())

    await client_for(server).complete(HELLO)

    request = server.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "http://model.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer secret-key"
    assert server.body() == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
        ],
    }


async def test_a_trailing_slash_on_the_base_url_makes_no_difference():
    server = Server(chat_response())

    await client_for(server, base_url=BASE_URL + "/").complete(HELLO)

    assert str(server.requests[0].url) == "http://model.test/v1/chat/completions"


async def test_temperature_and_max_tokens_are_sent_only_when_given():
    server = Server(chat_response())
    client = client_for(server)

    await client.complete(HELLO)
    await client.complete(HELLO, temperature=0.0, max_tokens=50)

    assert "temperature" not in server.body(0) and "max_tokens" not in server.body(0)
    assert server.body(1)["temperature"] == 0.0
    assert server.body(1)["max_tokens"] == 50


# The reply


async def test_returns_the_text_and_what_the_server_reported():
    completion = await client_for(Server(chat_response("Hello there."))).complete(HELLO)

    assert completion == Completion(
        text="Hello there.",
        model="served-model",
        finish_reason="stop",
        prompt_tokens=12,
        completion_tokens=3,
    )


async def test_a_cut_off_answer_says_so():
    reply = chat_response("Half an ans", finish_reason="length")

    assert (await client_for(Server(reply)).complete(HELLO)).finish_reason == "length"


async def test_a_reply_without_usage_has_no_token_counts():
    completion = await client_for(Server(chat_response(usage=False))).complete(HELLO)

    assert (completion.prompt_tokens, completion.completion_tokens) == (None, None)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{"index": 0, "finish_reason": "stop"}]},
        {"choices": [{"index": 0, "message": {"role": "assistant"}, "finish_reason": "stop"}]},
    ],
)
async def test_an_unreadable_reply_is_a_model_error_and_is_not_retried(body, waits):
    server = Server(httpx2.Response(200, json=body))

    with pytest.raises(ModelError) as caught:
        await client_for(server).complete(HELLO)

    assert type(caught.value) is ModelError
    assert len(server.requests) == 1


# Failures that are retried


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_a_temporary_failure_is_retried_and_then_succeeds(status, waits):
    server = Server(error(status), chat_response("Recovered."))

    completion = await client_for(server).complete(HELLO)

    assert completion.text == "Recovered."
    assert len(server.requests) == 2
    assert len(waits) == 1


@pytest.mark.parametrize(
    "failure",
    [
        httpx2.ConnectError("connection refused"),
        httpx2.ReadTimeout("timed out"),
    ],
)
async def test_a_dropped_connection_or_timeout_is_retried(failure, waits):
    server = Server(failure, chat_response("Recovered."))

    assert (await client_for(server).complete(HELLO)).text == "Recovered."
    assert len(server.requests) == 2


async def test_waits_double_between_attempts(waits):
    server = Server(error(503))

    with pytest.raises(ModelUnavailableError):
        await client_for(server, max_retries=3).complete(HELLO)

    # 0.5s, then 1s, then 2s, each shortened by up to a quarter at random.
    for wait, base in zip(waits, [0.5, 1.0, 2.0], strict=True):
        assert base * 0.75 <= wait <= base


async def test_a_retry_after_header_sets_the_wait(waits):
    server = Server(error(429, **{"retry-after": "7"}), chat_response())

    await client_for(server).complete(HELLO)

    assert waits == [7.0]


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_when_retries_run_out_the_endpoint_is_unavailable(status, waits):
    server = Server(error(status))

    with pytest.raises(ModelUnavailableError, match=str(status)):
        await client_for(server, max_retries=2).complete(HELLO)

    assert len(server.requests) == 3  # the first attempt and two retries


async def test_an_unreachable_endpoint_is_unavailable_once_retries_run_out(waits):
    server = Server(httpx2.ConnectError("connection refused"))

    with pytest.raises(ModelUnavailableError, match="could not reach"):
        await client_for(server, max_retries=1).complete(HELLO)

    assert len(server.requests) == 2


async def test_zero_retries_means_one_attempt(waits):
    server = Server(error(503))

    with pytest.raises(ModelUnavailableError):
        await client_for(server, max_retries=0).complete(HELLO)

    assert len(server.requests) == 1
    assert waits == []


# Failures that are not


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_a_refused_request_fails_at_once_with_its_status(status, waits):
    server = Server(error(status, "model 'test-model' not found"))

    with pytest.raises(ModelRequestError) as caught:
        await client_for(server).complete(HELLO)

    assert caught.value.status_code == status
    assert "not found" in str(caught.value)
    assert len(server.requests) == 1
    assert waits == []


async def test_a_long_error_body_is_cut_short_in_the_message(waits):
    server = Server(httpx2.Response(400, text="x" * 5000))

    with pytest.raises(ModelRequestError) as caught:
        await client_for(server).complete(HELLO)

    assert len(str(caught.value)) < 400


# Reasoning


async def test_reasoning_effort_is_sent_only_when_configured():
    server = Server(chat_response())

    await client_for(server).complete(HELLO)
    await client_for(server, reasoning_effort="none").complete(HELLO)

    assert "reasoning_effort" not in server.body(0)
    assert server.body(1)["reasoning_effort"] == "none"


# Streaming


def chunk(content=None, *, finish_reason=None, reasoning=None, usage=None, choices=True):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning"] = reasoning
    body = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "served-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
        if choices
        else [],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def sse(*chunks):
    """A server-sent event stream: one `data:` line per chunk, then the [DONE] marker."""
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode()
    )


async def collect(client, **options):
    return [event async for event in client.stream(HELLO, **options)]


async def test_streams_text_in_order_then_one_done_event():
    server = Server(
        sse(
            chunk("Tae "),
            chunk("studied "),
            chunk("at Vanderbilt.", finish_reason="stop"),
            chunk(choices=False, usage={"prompt_tokens": 40, "completion_tokens": 5}),
        )
    )

    events = await collect(client_for(server))

    assert events == [
        TextDelta("Tae "),
        TextDelta("studied "),
        TextDelta("at Vanderbilt."),
        StreamDone(
            model="served-model", finish_reason="stop", prompt_tokens=40, completion_tokens=5
        ),
    ]


async def test_asks_for_a_stream_with_token_counts():
    server = Server(sse(chunk("Hi", finish_reason="stop")))

    await collect(client_for(server, reasoning_effort="none"), max_tokens=20)

    body = server.body()
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 20
    assert body["reasoning_effort"] == "none"


async def test_hidden_reasoning_never_reaches_the_caller():
    server = Server(
        sse(
            chunk(reasoning="Thinking Process: the user wants..."),
            chunk(reasoning="so the answer is ready."),
            chunk("ready", finish_reason="stop"),
        )
    )

    events = await collect(client_for(server))

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["ready"]


async def test_a_stream_without_usage_has_no_token_counts():
    server = Server(sse(chunk("Hi", finish_reason="length")))

    done = (await collect(client_for(server)))[-1]

    assert done == StreamDone(model="served-model", finish_reason="length")


async def test_opening_a_stream_is_retried_like_any_request(waits):
    server = Server(error(503), sse(chunk("Recovered.", finish_reason="stop")))

    events = await collect(client_for(server))

    assert events[0] == TextDelta("Recovered.")
    assert len(server.requests) == 2


async def test_a_refused_stream_fails_at_once(waits):
    server = Server(error(401, "bad key"))

    with pytest.raises(ModelRequestError) as caught:
        await collect(client_for(server))

    assert caught.value.status_code == 401
    assert len(server.requests) == 1


async def test_a_stream_that_breaks_partway_is_unavailable_after_the_text_so_far():
    async def body():
        yield f"data: {json.dumps(chunk('Tae studied '))}\n\n".encode()
        raise httpx2.ReadError("connection reset")

    server = Server(
        httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body())
    )
    received = []

    with pytest.raises(ModelUnavailableError, match="broke partway"):
        async for event in client_for(server).stream(HELLO):
            received.append(event)

    assert received == [TextDelta("Tae studied ")]


# The fake, and building from settings


async def test_the_fake_replies_in_order_repeats_the_last_and_records_every_call():
    fake = FakeModelClient(["one", "two"])

    replies = [(await fake.complete(HELLO, max_tokens=5)).text for _ in range(3)]

    assert replies == ["one", "two", "two"]
    assert fake.calls[0] == (tuple(HELLO), {"temperature": None, "max_tokens": 5})
    assert len(fake.calls) == 3


async def test_the_fake_streams_its_reply_in_pieces_that_join_back_up():
    fake = FakeModelClient(["Tae studied at  Vanderbilt."])

    events = await collect(fake)

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert len(deltas) > 1
    assert "".join(deltas) == "Tae studied at  Vanderbilt."
    assert events[-1] == StreamDone(model="fake", finish_reason="stop")
    assert len(fake.calls) == 1


def test_the_fake_needs_at_least_one_reply():
    with pytest.raises(ValueError):
        FakeModelClient([])


async def test_the_client_is_built_from_the_three_model_settings(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "llama-3.3-70b-instruct")
    monkeypatch.setenv("MODEL_BASE_URL", "http://hosted.test/v1")
    monkeypatch.setenv("MODEL_API_KEY", "hosted-key")
    monkeypatch.setenv("MODEL_REASONING_EFFORT", "none")
    get_settings.cache_clear()
    server = Server(chat_response())

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    client = build_model_client(get_settings(), http_client=http)
    await client.complete(HELLO)

    assert client.model_name == "llama-3.3-70b-instruct"
    assert str(server.requests[0].url) == "http://hosted.test/v1/chat/completions"
    assert server.requests[0].headers["authorization"] == "Bearer hosted-key"
    assert server.body()["model"] == "llama-3.3-70b-instruct"
    assert server.body()["reasoning_effort"] == "none"


# The real endpoint, only with --run-llm


@pytest.mark.llm
async def test_the_configured_model_answers():
    client = build_model_client(get_settings())
    try:
        completion = await client.complete(
            [Message(role="user", content="Reply with one word: ready.")]
        )
    finally:
        await client.aclose()

    assert completion.text.strip()
    assert completion.finish_reason == "stop"


@pytest.mark.llm
async def test_the_configured_model_streams():
    client = build_model_client(get_settings())
    try:
        events = [
            event
            async for event in client.stream(
                [Message(role="user", content="Reply with one word: ready.")]
            )
        ]
    finally:
        await client.aclose()

    assert any(isinstance(e, TextDelta) and e.text.strip() for e in events)
    assert isinstance(events[-1], StreamDone)
