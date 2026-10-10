"""Dense retrieval: rank chunks by how close their vectors sit to the question's vector.

The question is embedded by the same model that embedded the chunks, so both land in the
same space. Postgres then orders the stored vectors by cosine distance to it. Every vector
is unit length, so cosine similarity is 1 minus that distance: 1 is the same direction, 0
is unrelated, and negative points away.

With enough rows, Postgres answers that ORDER BY through the HNSW index from migration
0002 instead of measuring every vector, which makes the result approximate. At a few
hundred rows it usually measures every vector anyway, because that is cheaper. The SQL is
the same either way.
"""

from __future__ import annotations

from typing import Any

import psycopg

from portfolio_bot.db.vector import vector_literal
from portfolio_bot.ingest.embedder import Embedder
from portfolio_bot.logging_config import get_logger
from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk

logger = get_logger(__name__)

Connection = psycopg.Connection[dict[str, Any]]

# The largest hnsw.ef_search pgvector accepts. A property of the extension, not a setting.
HNSW_EF_SEARCH_MAX = 1000


class DenseRetriever:
    """Vector search over `chunk_embeddings`, restricted to the embedder's own model.

    Only vectors made by the same model and revision as `embedder` are ranked. Two models
    place text in unrelated coordinate systems, so comparing a question from one against a
    chunk from another yields a number with no meaning. If any are present, the search
    leaves them out and logs a warning naming them.
    """

    name = "dense"

    def __init__(self, conn: Connection, embedder: Embedder, *, ef_search: int) -> None:
        self._conn = conn
        self._embedder = embedder
        self._ef_search = ef_search

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        vector = vector_literal(self._embedder.embed_query(query))
        model = {"name": self._embedder.model_name, "revision": self._embedder.model_revision}

        with self._conn.transaction():
            self._warn_about_other_models(model)
            # The index can return no more rows than its shortlist holds, so a k above
            # ef_search would be cut short without any error. The third argument makes the
            # setting local to this transaction, so it never leaks into whatever runs next
            # on a pooled connection.
            ef_search = min(max(self._ef_search, k), HNSW_EF_SEARCH_MAX)
            self._conn.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(ef_search),))
            rows = self._conn.execute(
                """
                SELECT c.id AS chunk_id, c.document_id, d.source_path, d.title,
                       c.heading_path, c.ordinal, c.text, c.char_start, c.char_end,
                       e.embedding <=> %(query)s::vector AS distance
                FROM chunk_embeddings e
                JOIN chunks c ON c.id = e.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE e.model_name = %(name)s
                  AND e.model_revision = %(revision)s
                ORDER BY e.embedding <=> %(query)s::vector
                LIMIT %(k)s
                """,
                {"query": vector, "k": k, **model},
            ).fetchall()

        return [
            ScoredChunk(
                chunk=RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    source_path=row["source_path"],
                    title=row["title"],
                    heading_path=tuple(row["heading_path"]),
                    ordinal=row["ordinal"],
                    text=row["text"],
                    char_start=row["char_start"],
                    char_end=row["char_end"],
                ),
                score=1.0 - float(row["distance"]),
                provenance=(Provenance(strategy=self.name, rank=rank),),
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def _warn_about_other_models(self, model: dict[str, str]) -> None:
        """Log the embeddings this search is skipping because another model made them.

        This reads every row of chunk_embeddings, which costs nothing at this corpus size
        and would not stay free at a much larger one.
        """
        others = self._conn.execute(
            """
            SELECT model_name, model_revision, count(*) AS n
            FROM chunk_embeddings
            WHERE model_name <> %(name)s OR model_revision <> %(revision)s
            GROUP BY model_name, model_revision
            ORDER BY model_name, model_revision
            """,
            model,
        ).fetchall()
        if not others:
            return
        logger.warning(
            "skipping embeddings made by a different model; run 'pb ingest' to re-embed them",
            extra={
                "skipped": sum(row["n"] for row in others),
                "models": [f"{row['model_name']}@{row['model_revision']}" for row in others],
            },
        )
