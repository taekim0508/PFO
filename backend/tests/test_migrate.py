"""Tests for the migration runner.

Split in two. Discovery and ordering are pure functions over files on disk and need no
database. Applying, idempotency, rollback, and drift detection are only meaningful against
real Postgres, so they run against the empty_database fixture from conftest.py, which builds
a throwaway database for each test and drops it afterwards. Nothing here mocks the database.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from portfolio_bot.db.migrate import (
    MIGRATIONS_DIR,
    Migration,
    MigrationError,
    discover_migrations,
    run_migrations,
)

# A 384-dimension vector, written the way Postgres accepts a vector literal. The real
# values come from the embedding model in phase 2; here only the width matters.
SAMPLE_EMBEDDING = "[" + ",".join(["0.1"] * 384) + "]"


def write_migration(directory: Path, filename: str, sql_text: str = "SELECT 1;") -> Path:
    """Write a migration file into `directory` and return its path."""
    path = directory / filename
    path.write_text(sql_text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Discovery. No database.
# ---------------------------------------------------------------------------


def test_discovers_nothing_in_an_empty_directory(tmp_path):
    assert discover_migrations(tmp_path) == []


def test_missing_directory_is_an_error(tmp_path):
    with pytest.raises(MigrationError, match="does not exist"):
        discover_migrations(tmp_path / "nope")


def test_returns_migrations_in_ascending_numeric_order(tmp_path):
    # Discovery reads the directory in whatever order the filesystem gives it, so the
    # ordering here is the runner's doing. Note that this does not prove the sort key is
    # the parsed number: the four-digit width the filename pattern enforces makes an
    # alphabetical sort agree with a numeric one. Enforcing that width is what actually
    # guarantees the order, and test_rejects_a_filename_that_does_not_match_the_pattern
    # is what holds it in place.
    for filename in ("0010_tenth.sql", "0002_second.sql", "0001_first.sql"):
        write_migration(tmp_path, filename)

    assert [m.filename for m in discover_migrations(tmp_path)] == [
        "0001_first.sql",
        "0002_second.sql",
        "0010_tenth.sql",
    ]
    assert [m.number for m in discover_migrations(tmp_path)] == [1, 2, 10]


@pytest.mark.parametrize(
    "filename",
    ["initial.sql", "1_initial.sql", "0001-initial.sql", "0001_Initial.sql", "0001_initial.txt"],
)
def test_rejects_a_filename_that_does_not_match_the_pattern(tmp_path, filename):
    write_migration(tmp_path, filename)

    with pytest.raises(MigrationError, match=filename):
        discover_migrations(tmp_path)


def test_rejects_two_migrations_sharing_a_number(tmp_path):
    write_migration(tmp_path, "0001_first.sql")
    write_migration(tmp_path, "0001_also_first.sql")

    with pytest.raises(MigrationError, match="share the number 0001"):
        discover_migrations(tmp_path)


def test_reads_contents_and_checksums_them(tmp_path):
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")

    (migration,) = discover_migrations(tmp_path)
    assert migration.sql == "CREATE TABLE example (id int);\n"
    assert len(migration.checksum) == 64
    assert isinstance(migration, Migration)


def test_the_real_migrations_directory_is_discoverable():
    # The runner is only useful if it can find the migrations the project actually ships.
    assert [m.filename for m in discover_migrations(MIGRATIONS_DIR)] == [
        "0001_initial.sql",
        "0002_indexes.sql",
    ]


# ---------------------------------------------------------------------------
# Applying. Real Postgres.
# ---------------------------------------------------------------------------


def table_names(database_url: str) -> set[str]:
    """Return the names of every table in the public schema."""
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    return {str(name) for (name,) in rows}


@pytest.mark.database
def test_first_run_creates_the_schema(empty_database):
    applied = run_migrations(empty_database)

    # Listed rather than derived from discover_migrations, which is what the runner itself
    # calls: comparing the runner against its own input would pass no matter what it did.
    assert applied == ["0001_initial.sql", "0002_indexes.sql"]
    assert {"documents", "chunks", "chunk_embeddings"} <= table_names(empty_database)


@pytest.mark.database
def test_second_run_changes_nothing(empty_database):
    run_migrations(empty_database)

    assert run_migrations(empty_database) == []

    with psycopg.connect(empty_database) as conn:
        rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    assert [name for (name,) in rows] == ["0001_initial.sql", "0002_indexes.sql"]


@pytest.mark.database
def test_a_document_chunk_and_embedding_round_trip(empty_database):
    run_migrations(empty_database)

    with psycopg.connect(empty_database) as conn:
        (document_id,) = conn.execute(
            "INSERT INTO documents (source_path, title, content_hash) "
            "VALUES (%s, %s, %s) RETURNING id",
            ("content/about.md", "About", "abc123"),
        ).fetchone()
        (chunk_id,) = conn.execute(
            "INSERT INTO chunks "
            "(document_id, ordinal, text, token_count, heading_path, char_start, char_end) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (document_id, 0, "some text", 2, ["Projects", "Portfolio Bot"], 0, 9),
        ).fetchone()
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, model_revision) "
            "VALUES (%s, %s, %s, %s)",
            (chunk_id, SAMPLE_EMBEDDING, "BAAI/bge-small-en-v1.5", "5c38ec7"),
        )

        text, heading_path = conn.execute(
            "SELECT text, heading_path FROM chunks WHERE id = %s", (chunk_id,)
        ).fetchone()
        assert text == "some text"
        # Stored as an array, so the innermost heading is addressable on its own.
        assert heading_path == ["Projects", "Portfolio Bot"]

        (dimensions,) = conn.execute(
            "SELECT vector_dims(embedding) FROM chunk_embeddings WHERE chunk_id = %s",
            (chunk_id,),
        ).fetchone()
        assert dimensions == 384


@pytest.mark.database
def test_deleting_a_document_cascades(empty_database):
    run_migrations(empty_database)

    with psycopg.connect(empty_database) as conn:
        (document_id,) = conn.execute(
            "INSERT INTO documents (source_path, title, content_hash) "
            "VALUES ('content/about.md', 'About', 'abc123') RETURNING id"
        ).fetchone()
        (chunk_id,) = conn.execute(
            "INSERT INTO chunks "
            "(document_id, ordinal, text, token_count, char_start, char_end) "
            "VALUES (%s, 0, 'some text', 2, 0, 9) RETURNING id",
            (document_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, model_revision) "
            "VALUES (%s, %s, 'm', 'r')",
            (chunk_id, SAMPLE_EMBEDDING),
        )

        conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))

        (chunks,) = conn.execute("SELECT count(*) FROM chunks").fetchone()
        (embeddings,) = conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone()
        assert (chunks, embeddings) == (0, 0)


@pytest.mark.database
def test_a_failing_migration_leaves_no_trace(empty_database, tmp_path):
    # 0002 creates a table and then contains invalid SQL. Both halves must be undone.
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", tmp_path / "0001_initial.sql")
    write_migration(
        tmp_path,
        "0002_bad.sql",
        "CREATE TABLE half_created (id int);\nTHIS IS NOT SQL;\n",
    )

    with pytest.raises(psycopg.errors.SyntaxError):
        run_migrations(empty_database, tmp_path)

    assert "half_created" not in table_names(empty_database)
    with psycopg.connect(empty_database) as conn:
        rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    # 0001 ran in its own transaction and stands; 0002 left nothing behind.
    assert [name for (name,) in rows] == ["0001_initial.sql"]


@pytest.mark.database
def test_editing_an_applied_migration_is_refused(empty_database, tmp_path):
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    run_migrations(empty_database, tmp_path)

    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id bigint);\n")

    with pytest.raises(MigrationError, match="has changed since it was applied"):
        run_migrations(empty_database, tmp_path)


@pytest.mark.database
def test_an_unchanged_applied_migration_passes_the_check(empty_database, tmp_path):
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    run_migrations(empty_database, tmp_path)

    assert run_migrations(empty_database, tmp_path) == []


@pytest.mark.database
def test_a_migration_applied_but_missing_from_disk_is_tolerated(empty_database, tmp_path):
    # Happens legitimately on an older checkout, so it warns rather than failing.
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    write_migration(tmp_path, "0002_second.sql", "CREATE TABLE other (id int);\n")
    run_migrations(empty_database, tmp_path)

    (tmp_path / "0002_second.sql").unlink()

    assert run_migrations(empty_database, tmp_path) == []


# ---------------------------------------------------------------------------
# Indexes. Real Postgres.
#
# Existing does not mean used. An index built with the wrong operator class, or an
# expression index the query spells differently, appears in pg_indexes and is then ignored
# by every query it was meant to serve, with nothing failing to say so. So one test checks
# that the indexes exist and two check that the planner actually reaches for them.
# ---------------------------------------------------------------------------

# Distinct wording per chunk so the full-text test matches one row rather than all of them.
CHUNK_TEXTS = [
    "Postgres and pgvector store the corpus and its embeddings in one system.",
    "The chunker splits markdown on headings and keeps character offsets.",
    "Reciprocal rank fusion merges the two retrieval arms into one ranking.",
    "The generation layer speaks an OpenAI-compatible protocol to an open-weight model.",
    "Migrations are numbered SQL files applied once each inside a transaction.",
]


def seed_chunks(conn) -> None:
    """Insert one document with several chunks and embeddings, then update the statistics.

    ANALYZE matters here. The planner chooses on estimated cost, and on a table it has
    never looked at it works from defaults that have nothing to do with what is really
    there, which makes a plan assertion a coin flip.
    """
    (document_id,) = conn.execute(
        "INSERT INTO documents (source_path, title, content_hash) "
        "VALUES ('content/about.md', 'About', 'abc123') RETURNING id"
    ).fetchone()

    for ordinal, text in enumerate(CHUNK_TEXTS):
        (chunk_id,) = conn.execute(
            "INSERT INTO chunks "
            "(document_id, ordinal, text, token_count, char_start, char_end) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (document_id, ordinal, text, len(text.split()), 0, len(text)),
        ).fetchone()
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding, model_name, model_revision) "
            "VALUES (%s, %s, 'm', 'r')",
            (chunk_id, SAMPLE_EMBEDDING),
        )

    conn.execute("ANALYZE documents, chunks, chunk_embeddings")


def query_plan(conn, query: str) -> str:
    """Return the plan for `query` as one string, with sequential scans discouraged.

    On five rows a sequential scan is genuinely the cheapest way to answer anything, so the
    planner would ignore both indexes no matter how well they were built. Turning seqscan
    off removes that confound and leaves the question these tests are actually asking: given
    that the planner wants to use an index, is there one it can use for this query.
    """
    conn.execute("SET enable_seqscan = off")
    rows = conn.execute("EXPLAIN " + query).fetchall()
    return "\n".join(str(line) for (line,) in rows)


@pytest.mark.database
def test_the_index_migration_creates_both_retrieval_indexes(empty_database):
    run_migrations(empty_database)

    with psycopg.connect(empty_database) as conn:
        rows = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename IN ('chunks', 'chunk_embeddings')"
        ).fetchall()

    indexes = {str(name) for (name,) in rows}
    assert "chunk_embeddings_embedding_hnsw" in indexes
    assert "chunks_text_fts" in indexes
    # The lookup path for a document's chunks, in reading order, which is why 0002 does not
    # add a second index on document_id alone.
    assert "chunks_document_id_ordinal_key" in indexes


@pytest.mark.database
def test_the_vector_index_serves_a_cosine_similarity_search(empty_database):
    run_migrations(empty_database)

    with psycopg.connect(empty_database) as conn:
        seed_chunks(conn)

        plan = query_plan(
            conn,
            "SELECT chunk_id FROM chunk_embeddings "
            f"ORDER BY embedding <=> '{SAMPLE_EMBEDDING}'::vector LIMIT 3",
        )

    # <=> is cosine distance, and only an index built with vector_cosine_ops answers it.
    # Build this index with vector_l2_ops instead and this is the assertion that fails.
    assert "chunk_embeddings_embedding_hnsw" in plan


@pytest.mark.database
def test_the_text_index_serves_a_full_text_search(empty_database):
    run_migrations(empty_database)

    with psycopg.connect(empty_database) as conn:
        seed_chunks(conn)

        plan = query_plan(
            conn,
            "SELECT id FROM chunks "
            "WHERE to_tsvector('english', text) @@ plainto_tsquery('english', 'splitting')",
        )
        matches = conn.execute(
            "SELECT ordinal FROM chunks "
            "WHERE to_tsvector('english', text) @@ plainto_tsquery('english', 'splitting')"
        ).fetchall()

    # The index is on an expression, so the query has to spell that expression the same way
    # to get it. Changing the language in the migration and not here breaks this test, which
    # is the point of asserting on the plan rather than only on the result.
    assert "chunks_text_fts" in plan
    # And the stemming is doing real work: the corpus says "splits", the query says
    # "splitting", and both reduce to the lexeme 'split'.
    assert [ordinal for (ordinal,) in matches] == [1]
