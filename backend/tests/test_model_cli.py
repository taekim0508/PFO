"""`pb model ping` sends one prompt and prints what came back, or why nothing did."""

from portfolio_bot.cli import PING_PROMPT, build_parser, command_model, main
from portfolio_bot.generation.client import (
    FakeModelClient,
    Message,
    ModelError,
    ModelRequestError,
    ModelUnavailableError,
)
from portfolio_bot.settings import get_settings


def ping(client, *argv):
    args = build_parser().parse_args(["model", "ping", *argv])
    return command_model(get_settings(), args, client=client)


class FailingClient:
    """A model client that raises the error it was given."""

    model_name = "failing-model"

    def __init__(self, error):
        self._error = error

    async def complete(self, messages, *, temperature=None, max_tokens=None):
        raise self._error


def test_prints_the_reply_the_model_and_the_latency(capsys):
    assert ping(FakeModelClient(["ready"], model="qwen3.5:9b")) == 0

    out = capsys.readouterr().out
    assert out.startswith("qwen3.5:9b at http://localhost:11434/v1\n")
    assert "reply:        ready" in out
    assert "answered by:  qwen3.5:9b" in out
    assert "finish:       stop" in out
    assert "latency:" in out


def test_sends_the_default_prompt_as_one_user_message():
    fake = FakeModelClient()

    ping(fake)

    assert fake.calls[0][0] == (Message(role="user", content=PING_PROMPT),)


def test_prompt_can_be_chosen():
    fake = FakeModelClient()

    ping(fake, "--prompt", "Say hi")

    assert fake.calls[0][0] == (Message(role="user", content="Say hi"),)


def test_a_multi_line_reply_prints_on_one_line(capsys):
    ping(FakeModelClient(["ready\n\nand waiting"]))

    assert "reply:        ready and waiting\n" in capsys.readouterr().out


def test_token_counts_the_server_did_not_report_say_so(capsys):
    ping(FakeModelClient())  # the fake reports none

    assert "tokens:       not reported" in capsys.readouterr().out


def test_an_unreachable_endpoint_exits_1_and_points_at_make_model_up(capsys):
    error = ModelUnavailableError("could not reach the model endpoint: connection refused")

    assert ping(FailingClient(error)) == 1

    err = capsys.readouterr().err
    assert "Cannot get an answer from http://localhost:11434/v1" in err
    assert "make model-up" in err


def test_a_refused_request_exits_1_and_names_the_settings_to_check(capsys):
    assert ping(FailingClient(ModelRequestError(404, "model not found"))) == 1

    err = capsys.readouterr().err
    assert "404" in err
    assert "MODEL_NAME and MODEL_API_KEY" in err


def test_an_unreadable_reply_exits_1(capsys):
    assert ping(FailingClient(ModelError("replied without any text"))) == 1

    assert "not in a readable form" in capsys.readouterr().err


def test_model_without_a_subcommand_prints_usage_and_exits_2(capsys):
    assert main(["model"]) == 2

    assert "pb model ping" in capsys.readouterr().err
