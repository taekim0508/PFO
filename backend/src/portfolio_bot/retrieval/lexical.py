"""Lexical retrieval: rank chunks by the words they share with the question.

Postgres reduces both the chunk and the question to lexemes: lowercased, common words like
"the" and "where" dropped, each remaining word cut to its stem, so "results" and "result"
are the same key. The GIN index from migration 0002 maps every lexeme to the chunks that
contain it, so finding the chunks that share a lexeme with the question is a lookup rather
than a scan.

A chunk matches if it shares any lexeme with the question. Requiring all of them returned
nothing for every realistic question tried on the corpus, because a natural question
carries words like "go" or a name that rarely all land in one chunk.

`ts_rank_cd` scores a match by how many of the question's lexemes the chunk contains and
how close together they sit. It does not weigh how rare a word is, so a match on
"vanderbilt" counts the same as a match on "go". That is what BM25 adds (roadmap 8.2).
"""

from __future__ import annotations

from typing import Any

import psycopg

from portfolio_bot.retrieval.base import Provenance, RetrievedChunk, ScoredChunk

Connection = psycopg.Connection[dict[str, Any]]

# The question as an any-word query. plainto_tsquery does the reducing and joins the
# lexemes with & (all of them); swapping that for | makes it any of them. Every lexeme in
# its output is quoted, so a stray & inside one stays text and cannot become syntax.
_ANY_WORD_QUERY = "replace(plainto_tsquery('english', %(query)s)::text, '&', '|')::tsquery"

# Spelled exactly as the expression index in 0002 is. A variant that merely means the same
# thing would be invisible to the planner, and every search would read the whole table.
_CHUNK_LEXEMES = "to_tsvector('english', c.text)"


# Module level so a test can EXPLAIN exactly the query that runs.
SEARCH_SQL = f"""
    SELECT c.id AS chunk_id, c.document_id, d.source_path, d.title,
           c.heading_path, c.ordinal, c.text, c.char_start, c.char_end,
           ts_rank_cd({_CHUNK_LEXEMES}, {_ANY_WORD_QUERY}) AS score
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE {_CHUNK_LEXEMES} @@ {_ANY_WORD_QUERY}
    ORDER BY score DESC, c.id
    LIMIT %(k)s
"""


class LexicalRetriever:
    """Postgres full-text search over every chunk, ranked with ts_rank_cd.

    Searches chunk text alone, not titles or the heading path above a chunk, which is what
    the index covers. Ties, common because scores count matches rather than weigh them,
    are broken by chunk id so the same question always returns the same order.
    """

    name = "lexical"

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        if k < 1:
            raise ValueError(f"k must be at least 1, got {k}")
        rows = self._conn.execute(SEARCH_SQL, {"query": query, "k": k}).fetchall()

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
                score=float(row["score"]),
                provenance=(Provenance(strategy=self.name, rank=rank),),
            )
            for rank, row in enumerate(rows, start=1)
        ]
