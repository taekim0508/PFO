"""The one client every generation call goes through, for any OpenAI-compatible endpoint.

Ollama, Together, Groq, Fireworks, and DeepInfra all accept the request shape OpenAI's
chat-completions API defined: a list of role-tagged messages in, a reply out. So one
implementation covers all of them, and the model name, base URL, and API key are the only
things that change between them. Those are settings, which is what makes swapping models
configuration rather than code.

A model keeps no memory between calls. Every request carries the whole conversation, and
the reply says why the model stopped: `stop` means it finished, `length` means it ran out
of tokens mid-answer and the text is cut off.

Retries are the SDK's: it retries rate limits (429), lock and request timeouts (408, 409),
server errors (5xx), dropped connections, and timeouts, waiting 0.5s and doubling up to
8s with some randomness, or as long as a `Retry-After` header asks. This module sets how
many times and translates what is left when they run out into the errors below, so
callers never import the SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

import httpx2
import openai
from openai.types.chat import ChatCompletionMessageParam

from portfolio_bot.settings import Settings

Role = Literal["system", "user", "assistant"]

# Status codes the SDK retries. Reaching the caller with one of these means retries ran out.
_RETRIED_STATUSES = frozenset({408, 409, 429})

# How much of an error response body to keep in the exception message.
_BODY_EXCERPT_CHARS = 300


@dataclass(frozen=True)
class Message:
    """One turn of a conversation."""

    role: Role
    content: str


@dataclass(frozen=True)
class Completion:
    """A model's reply, and what the server reported about producing it.

    `model` is what the server says answered, which can differ from the name requested
    (a provider may resolve an alias). Token counts are None when the server omits them.
    """

    text: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelError(Exception):
    """A generation call failed. Also raised directly for a reply that cannot be read."""


class ModelRequestError(ModelError):
    """The endpoint refused the request: a bad key, an unknown model, a malformed request.

    Retrying would get the same answer, so it is never retried.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"model endpoint returned {status_code}: {message}")
        self.status_code = status_code


class ModelUnavailableError(ModelError):
    """The endpoint could not be reached or kept failing, and the retries ran out."""


class ModelClient(Protocol):
    """Anything that can answer a conversation. Streaming joins this in roadmap 4.4."""

    @property
    def model_name(self) -> str: ...

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion: ...


class OpenAICompatibleClient:
    """A `ModelClient` for any endpoint that speaks the chat-completions shape.

    `timeout` is per attempt, in seconds. `max_retries` counts attempts after the first.
    `http_client` is for tests, which pass one with a fake transport so nothing leaves the
    process.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        # Sent only when given, so an endpoint's own defaults apply otherwise.
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["max_tokens"] = max_tokens

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[_to_param(message) for message in messages],
                **options,
            )
        except openai.APIStatusError as error:
            status = error.status_code
            if status in _RETRIED_STATUSES or status >= 500:
                raise ModelUnavailableError(
                    f"model endpoint still returned {status} after retries"
                ) from error
            raise ModelRequestError(status, _excerpt(error.response.text)) from error
        except openai.APIConnectionError as error:
            # APITimeoutError is a subclass, so a timeout that outlasted the retries lands
            # here too.
            raise ModelUnavailableError(f"could not reach the model endpoint: {error}") from error

        # The SDK builds its response objects without validating them, so a reply missing
        # a field surfaces as a missing attribute rather than an exception.
        choices = getattr(response, "choices", None)
        if not choices:
            raise ModelError("model endpoint replied without any choices")
        message = getattr(choices[0], "message", None)
        text = getattr(message, "content", None)
        if not isinstance(text, str):
            raise ModelError("model endpoint replied without any text")

        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            model=getattr(response, "model", None) or self._model,
            finish_reason=getattr(choices[0], "finish_reason", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )

    async def aclose(self) -> None:
        """Close the underlying connections."""
        await self._client.close()


class FakeModelClient:
    """A `ModelClient` for tests: replies from a script and records what it was sent.

    Replies come back in order, and the last one repeats once the script runs out.
    """

    def __init__(self, replies: Sequence[str] = ("fake reply",), model: str = "fake") -> None:
        if not replies:
            raise ValueError("a FakeModelClient needs at least one reply")
        self._replies = list(replies)
        self._model = model
        self.calls: list[tuple[tuple[Message, ...], dict[str, Any]]] = []

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        self.calls.append((tuple(messages), {"temperature": temperature, "max_tokens": max_tokens}))
        text = self._replies[min(len(self.calls), len(self._replies)) - 1]
        return Completion(text=text, model=self._model, finish_reason="stop")


def build_model_client(
    settings: Settings, *, http_client: httpx2.AsyncClient | None = None
) -> OpenAICompatibleClient:
    """The client the settings describe. The one place settings become a client."""
    return OpenAICompatibleClient(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model=settings.model_name,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        http_client=http_client,
    )


def _to_param(message: Message) -> ChatCompletionMessageParam:
    return cast(ChatCompletionMessageParam, {"role": message.role, "content": message.content})


def _excerpt(body: str) -> str:
    body = " ".join(body.split())
    if len(body) <= _BODY_EXCERPT_CHARS:
        return body
    return body[:_BODY_EXCERPT_CHARS] + "..."
