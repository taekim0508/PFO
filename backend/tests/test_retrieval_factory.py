"""The factory turns a strategy name into the strategy that answers to it."""

import pytest

from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.retrieval.dense import DenseRetriever
from portfolio_bot.retrieval.factory import STRATEGY_NAMES, build_strategy
from portfolio_bot.retrieval.lexical import LexicalRetriever
from portfolio_bot.settings import get_settings


@pytest.mark.parametrize(
    ("name", "cls"), [("dense", DenseRetriever), ("lexical", LexicalRetriever)]
)
def test_builds_the_strategy_named(name, cls):
    # Building a strategy touches neither the connection nor the model, so none is needed.
    strategy = build_strategy(name, None, FakeEmbedder(), get_settings())

    assert isinstance(strategy, cls)
    assert strategy.name == name


def test_every_offered_name_can_be_built():
    for name in STRATEGY_NAMES:
        assert build_strategy(name, None, FakeEmbedder(), get_settings()).name == name


def test_an_unknown_name_is_refused():
    with pytest.raises(ValueError, match="telepathy"):
        build_strategy("telepathy", None, FakeEmbedder(), get_settings())
