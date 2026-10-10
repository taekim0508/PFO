"""Build a retrieval strategy from its name.

The one place that knows which class answers to which name, so `pb search`, the evaluation
harness, and the API can all choose a strategy from a string without importing each class.
"""

from __future__ import annotations

from portfolio_bot.ingest.embedder import Embedder
from portfolio_bot.retrieval.base import RetrievalStrategy
from portfolio_bot.retrieval.dense import Connection, DenseRetriever
from portfolio_bot.retrieval.lexical import LexicalRetriever
from portfolio_bot.settings import Settings

STRATEGY_NAMES = ("dense", "lexical")


def build_strategy(
    name: str, conn: Connection, embedder: Embedder, settings: Settings
) -> RetrievalStrategy:
    """The strategy called `name`, ready to search over `conn`.

    Every strategy is handed the same arguments and takes what it needs. The embedder loads
    its model on first use, so passing one to a strategy that never embeds costs nothing.
    """
    if name == "dense":
        return DenseRetriever(conn, embedder, ef_search=settings.hnsw_ef_search)
    if name == "lexical":
        return LexicalRetriever(conn)
    raise ValueError(f"unknown retrieval strategy {name!r}; expected one of {STRATEGY_NAMES}")
