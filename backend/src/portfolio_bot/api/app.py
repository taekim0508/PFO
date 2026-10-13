"""The FastAPI application: health, and a chat endpoint that streams an answer as events.

Run it with `make dev`, which starts uvicorn on `create_app` as a factory. A factory,
rather than a module-level `app`, so importing this module reads no settings and opens no
connections; tests build their own app with fakes.

At startup the connection pool opens (failing fast on a bad DATABASE_URL, as D30 decided)
and the embedding model loads once, so no visitor's first question waits on either. Both
are released at shutdown.

`POST /api/chat` answers with Server-Sent Events: `sources`, then `delta`s, then `done`, or
`error` in place of `done`. Rate limiting happens before the stream opens, so a refused
request is a plain 429. Once streaming has begun the status is already 200, which is why
every later failure is an `error` event rather than a status code. Whatever goes wrong,
the visitor gets a short sentence; the details go to the log.
"""

from __future__ import annotations

import asyncio
import math
import subprocess
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg_pool import PoolTimeout
from pydantic import BaseModel

from portfolio_bot.api.rate_limit import RateLimiter
from portfolio_bot.api.schemas import (
    ChatRequest,
    DeltaEvent,
    DoneEvent,
    ErrorCode,
    ErrorEvent,
    HealthOut,
    SourcesEvent,
)
from portfolio_bot.db.pool import close_pool, connection, get_pool
from portfolio_bot.generation.ask import AnswerDone, Sources, ask
from portfolio_bot.generation.client import (
    ModelClient,
    ModelError,
    ModelUnavailableError,
    TextDelta,
    build_model_client,
)
from portfolio_bot.generation.prompt import PROMPT_VERSION
from portfolio_bot.ingest.embedder import Embedder, build_embedder
from portfolio_bot.logging_config import configure_logging, get_logger
from portfolio_bot.retrieval.factory import build_strategy
from portfolio_bot.settings import REPO_ROOT, Settings, get_settings

logger = get_logger(__name__)

# What a visitor reads for each failure. Never a stack trace, a host, or a setting.
ERROR_MESSAGES: dict[ErrorCode, str] = {
    "model_unavailable": "The model isn't answering right now. Please try again in a minute.",
    "model_error": "Something went wrong while writing the answer. Please try again.",
    "database_unavailable": "The bot can't reach its notes right now. Please try again shortly.",
    "timeout": "That took too long to answer. Please try again.",
    "internal": "Something went wrong. Please try again.",
}


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    client: ModelClient | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """Build the app. Tests pass a fake `embedder` and `client`, and a `clock` for limits."""
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings)
        get_pool()
        active_embedder = embedder if embedder is not None else build_embedder(settings)
        # Loads the model now rather than inside the first visitor's request.
        await asyncio.to_thread(active_embedder.embed_query, "warm up")
        # Only a client built here is closed here; one passed in belongs to the caller.
        built = build_model_client(settings) if client is None else None
        active_client: ModelClient
        if built is not None:
            active_client = built
        else:
            assert client is not None
            active_client = client
        app.state.embedder = active_embedder
        app.state.client = active_client
        app.state.git_sha = settings.git_sha or _git_sha()
        logger.info("api started", extra={"model": active_client.model_name})
        try:
            yield
        finally:
            if built is not None:
                await built.aclose()
            close_pool()

    app = FastAPI(title="Portfolio bot", lifespan=lifespan)
    app.state.limiter = RateLimiter(
        per_minute=settings.rate_limit_per_minute,
        per_day=settings.rate_limit_per_day,
        clock=clock,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        problems = error.errors()
        message = str(problems[0].get("msg", "invalid request")) if problems else "invalid request"
        # Pydantic prefixes messages raised in validators with "Value error, ".
        message = message.removeprefix("Value error, ")
        return _error_json(422, "invalid_request", message)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"path": request.url.path})
        return _error_json(500, "internal", ERROR_MESSAGES["internal"])

    @app.get("/api/health")
    async def health(request: Request) -> JSONResponse:
        database = await asyncio.to_thread(_database_answers)
        body = HealthOut(
            status="ok" if database else "degraded",
            database=database,
            git_sha=request.app.state.git_sha,
            model=settings.model_name,
            prompt_version=PROMPT_VERSION,
        )
        return JSONResponse(body.model_dump(), status_code=200 if database else 503)

    @app.post("/api/chat", response_model=None)
    async def chat(body: ChatRequest, request: Request) -> StreamingResponse | JSONResponse:
        limiter: RateLimiter = request.app.state.limiter
        visitor = request.client.host if request.client else "unknown"
        limiter.forget_idle()
        wait = limiter.check(visitor)
        if wait is not None:
            response = _error_json(
                429, "rate_limited", "You've asked a lot of questions quickly. Please wait."
            )
            response.headers["Retry-After"] = str(math.ceil(wait))
            return response

        events = _answer_events(
            body,
            settings=settings,
            embedder=request.app.state.embedder,
            client=request.app.state.client,
        )
        return StreamingResponse(
            events,
            media_type="text/event-stream",
            # Proxies must pass each event through as it is written, not buffer the answer.
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


async def _answer_events(
    body: ChatRequest, *, settings: Settings, embedder: Embedder, client: ModelClient
) -> AsyncIterator[str]:
    """The ask pipeline's events as SSE frames, ending in `done` or `error`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.chat_deadline_seconds
    code: ErrorCode | None = None
    done: AnswerDone | None = None
    try:
        with connection() as conn:
            strategy = build_strategy(
                body.strategy or settings.default_strategy, conn, embedder, settings
            )
            events = ask(
                body.question,
                strategy=strategy,
                client=client,
                k=body.k or settings.top_k,
                token_budget=settings.context_token_budget,
                relevance_floor=settings.relevance_floor,
                temperature=settings.answer_temperature,
                max_tokens=settings.answer_max_tokens,
            )
            try:
                while True:
                    # The deadline covers the whole answer, so each wait gets what is left.
                    remaining = max(deadline - loop.time(), 0.0)
                    try:
                        event = await asyncio.wait_for(anext(events), timeout=remaining)
                    except StopAsyncIteration:
                        break
                    if isinstance(event, Sources):
                        yield _frame("sources", SourcesEvent.of(event))
                    elif isinstance(event, TextDelta):
                        yield _frame("delta", DeltaEvent(text=event.text))
                    else:
                        done = event
                        yield _frame("done", DoneEvent.of(event))
            finally:
                await events.aclose()
    except TimeoutError:
        code = "timeout"
    except ModelUnavailableError:
        code = "model_unavailable"
    except ModelError:
        code = "model_error"
    except (psycopg.Error, PoolTimeout):
        code = "database_unavailable"
    except Exception:
        logger.exception("chat failed")
        code = "internal"

    if code is not None:
        logger.warning("chat ended in an error", extra={"code": code})
        yield _frame("error", ErrorEvent(code=code, message=ERROR_MESSAGES[code]))
    elif done is not None:
        logger.info(
            "chat answered",
            extra={
                "question_chars": len(body.question),
                "no_context": done.no_context,
                "cited": list(done.cited),
                "total_ms": round(done.total_seconds * 1000),
            },
        )


def _frame(event: str, payload: BaseModel) -> str:
    """One Server-Sent Event: a name line, a data line of JSON, and a blank line."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


def _error_json(status: int, code: str, message: str) -> JSONResponse:
    content: dict[str, Any] = {"error": {"code": code, "message": message}}
    return JSONResponse(content, status_code=status)


def _database_answers() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return True
    except (psycopg.Error, PoolTimeout):
        return False


def _git_sha() -> str:
    """The checked-out commit, for local runs. A deploy passes GIT_SHA instead."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
