"""Mirror the content directory into the database: load, chunk, embed, write.

A document is re-processed only when it needs to be: its file changed, it is new, or some
of its chunks were embedded by a different model than the one running now. Everything else
is skipped. A file that has disappeared from disk takes its document with it, and its
chunks and embeddings follow by cascade.

Each document is written in its own transaction, so one bad file costs that file and
nothing else. Embedding happens before the transaction opens, because it is the slow part
and there is no reason to hold a transaction open while a model runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from portfolio_bot.ingest.chunker import Chunk, chunk_document
from portfolio_bot.ingest.embedder import EMBEDDING_MAX_TOKENS, Embedder
from portfolio_bot.ingest.loader import DocumentError, SourceDocument, discover, read_document
from portfolio_bot.logging_config import get_logger

logger = get_logger(__name__)

Connection = psycopg.Connection[dict[str, Any]]


@dataclass
class IngestReport:
    """What a run did, or with dry_run, what it would have done."""

    processed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    chunks_written: int = 0
    chunks_embedded: int = 0


@dataclass(frozen=True)
class _Stored:
    content_hash: str
    stale: bool


def ingest(
    conn: Connection,
    root: Path,
    embedder: Embedder,
    *,
    chunk_size: int,
    chunk_overlap: int,
    force: bool = False,
    dry_run: bool = False,
) -> IngestReport:
    """Bring the database in line with the markdown files under `root`.

    `force` re-processes every document whether or not it changed, which is what a change
    to the chunking settings needs, since those are not part of a file's hash. `dry_run`
    reads the database and the files and reports what would happen, writing and embedding
    nothing.
    """
    report = IngestReport()
    stored = _stored_documents(conn, embedder)
    on_disk: set[str] = set()

    for path in discover(root):
        source_path = path.relative_to(root).as_posix()
        on_disk.add(source_path)
        try:
            document = read_document(root, path)
        except DocumentError as error:
            logger.error("skipped unreadable document", extra={"path": source_path})
            report.failed.append((source_path, str(error)))
            continue

        previous = stored.get(source_path)
        if (
            not force
            and previous is not None
            and previous.content_hash == document.content_hash
            and not previous.stale
        ):
            report.unchanged.append(source_path)
            continue

        chunks = chunk_document(document.text, document.body_start, chunk_size, chunk_overlap)
        if dry_run:
            report.processed.append(source_path)
            report.chunks_written += len(chunks)
            continue

        try:
            embedded = _write_document(conn, document, chunks, embedder)
        except psycopg.Error as error:
            logger.error("failed to write document", extra={"path": source_path})
            report.failed.append((source_path, str(error)))
            continue
        report.processed.append(source_path)
        report.chunks_written += len(chunks)
        report.chunks_embedded += embedded
        logger.info("ingested document", extra={"path": source_path, "chunks": len(chunks)})

    for source_path in sorted(set(stored) - on_disk):
        if not dry_run:
            with conn.transaction():
                conn.execute("DELETE FROM documents WHERE source_path = %s", (source_path,))
            logger.info("deleted document", extra={"path": source_path})
        report.deleted.append(source_path)

    return report


def embedding_text(title: str, chunk: Chunk) -> str:
    """The text the model actually embeds for a chunk: where it sits, then what it says.

    A chunk from the middle of a long section often never names its subject. "It ranked
    four ways" means little alone and a lot under "AI Producer Internship > How retrieval
    narrows the candidate pool". The stored chunk text stays exactly the file's text, so
    offsets still hold; only the vector gets the extra context.
    """
    location = " > ".join([title, *chunk.heading_path])
    return f"{location}\n\n{chunk.text}"


def _stored_documents(conn: Connection, embedder: Embedder) -> dict[str, _Stored]:
    """Every stored document's hash, and whether any of its chunks needs re-embedding.

    A chunk needs it when it has no embedding at all, or one made by a different model or
    revision than `embedder`. Without this check, changing the embedding model would leave
    old vectors in place next to new ones, and the two are not comparable.
    """
    with conn.transaction():
        rows = conn.execute(
            """
            SELECT d.source_path, d.content_hash,
                   EXISTS (
                       SELECT 1
                       FROM chunks c
                       LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id
                       WHERE c.document_id = d.id
                         AND (e.chunk_id IS NULL
                              OR e.model_name <> %(name)s
                              OR e.model_revision <> %(revision)s)
                   ) AS stale
            FROM documents d
            """,
            {"name": embedder.model_name, "revision": embedder.model_revision},
        ).fetchall()
    return {
        row["source_path"]: _Stored(content_hash=row["content_hash"], stale=row["stale"])
        for row in rows
    }


def _write_document(
    conn: Connection, document: SourceDocument, chunks: Sequence[Chunk], embedder: Embedder
) -> int:
    """Replace one document's chunks and embeddings. Returns how many were embedded."""
    texts = [embedding_text(document.title, chunk) for chunk in chunks]
    vectors = embedder.embed(texts)
    token_counts = embedder.count_tokens(texts)
    for chunk, tokens in zip(chunks, token_counts, strict=True):
        if tokens > EMBEDDING_MAX_TOKENS:
            logger.warning(
                "chunk is longer than the embedding model reads; the end will be ignored",
                extra={"path": document.source_path, "ordinal": chunk.ordinal, "tokens": tokens},
            )

    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO documents (source_path, title, content_hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_path) DO UPDATE
                SET title = EXCLUDED.title,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = now()
            RETURNING id
            """,
            (document.source_path, document.title, document.content_hash),
        ).fetchone()
        assert row is not None
        document_id = row["id"]

        # Replacing every chunk is simpler than diffing old against new, and a document is
        # a few dozen chunks at most. Their embeddings go with them by cascade.
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        for chunk, vector, tokens in zip(chunks, vectors, token_counts, strict=True):
            chunk_row = conn.execute(
                """
                INSERT INTO chunks
                    (document_id, ordinal, text, token_count, heading_path, char_start, char_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    document_id,
                    chunk.ordinal,
                    chunk.text,
                    tokens,
                    list(chunk.heading_path),
                    chunk.char_start,
                    chunk.char_end,
                ),
            ).fetchone()
            assert chunk_row is not None
            conn.execute(
                """
                INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, model_revision)
                VALUES (%s, %s::vector, %s, %s)
                """,
                (
                    chunk_row["id"],
                    _vector_literal(vector),
                    embedder.model_name,
                    embedder.model_revision,
                ),
            )
    return len(chunks)


def _vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form, '[0.1,0.2,...]'. Saves a dependency on pgvector's adapter."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"
