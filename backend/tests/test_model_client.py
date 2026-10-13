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


def client_for(server, *, base_url=BASE_URL, max_retries=3):
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    return OpenAICompatibleClient(
        base_url=base_url,
        api_key="secret-key",
        model="test-model",
        timeout=5.0,
        max_retries=max_retries,
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


# The fake, and building from settings


async def test_the_fake_replies_in_order_repeats_the_last_and_records_every_call():
    fake = FakeModelClient(["one", "two"])

    replies = [(await fake.complete(HELLO, max_tokens=5)).text for _ in range(3)]

    assert replies == ["one", "two", "two"]
    assert fake.calls[0] == (tuple(HELLO), {"temperature": None, "max_tokens": 5})
    assert len(fake.calls) == 3


def test_the_fake_needs_at_least_one_reply():
    with pytest.raises(ValueError):
        FakeModelClient([])


async def test_the_client_is_built_from_the_three_model_settings(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "llama-3.3-70b-instruct")
    monkeypatch.setenv("MODEL_BASE_URL", "http://hosted.test/v1")
    monkeypatch.setenv("MODEL_API_KEY", "hosted-key")
    get_settings.cache_clear()
    server = Server(chat_response())

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    client = build_model_client(get_settings(), http_client=http)
    await client.complete(HELLO)

    assert client.model_name == "llama-3.3-70b-instruct"
    assert str(server.requests[0].url) == "http://hosted.test/v1/chat/completions"
    assert server.requests[0].headers["authorization"] == "Bearer hosted-key"
    assert server.body()["model"] == "llama-3.3-70b-instruct"


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
