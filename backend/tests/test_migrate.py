"""Tests for the migration runner.

Split in two. Discovery and ordering are pure functions over files on disk and need no
database. Applying, idempotency, rollback, and drift detection are only meaningful against
real Postgres, so they run against a throwaway database created for each test and dropped
afterwards. Nothing here mocks the database.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from portfolio_bot.db.migrate import (
    MIGRATIONS_DIR,
    Migration,
    MigrationError,
    discover_migrations,
    run_migrations,
)
from portfolio_bot.settings import get_settings

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
    assert [m.filename for m in discover_migrations(MIGRATIONS_DIR)] == ["0001_initial.sql"]


# ---------------------------------------------------------------------------
# Applying. Real Postgres.
# ---------------------------------------------------------------------------


@pytest.fixture
def throwaway_database(request):
    """Create an empty database for one test, yield its URL, and drop it afterwards.

    The developer's DATABASE_URL is used only to reach the server. The database it names
    is never touched: this connects to the `postgres` maintenance database alongside it,
    creates a randomly named database, and drops that at the end.

    This is deliberately local to this file. Roadmap 1.5 generalizes it into conftest.py
    for the whole suite and is expected to replace it.
    """
    if request.node.get_closest_marker("database") is None:
        raise RuntimeError("throwaway_database requires the 'database' marker")

    parts = conninfo_to_dict(get_settings().database_url)
    maintenance_url = make_conninfo(**{**parts, "dbname": "postgres"})

    try:
        with psycopg.connect(maintenance_url, autocommit=True, connect_timeout=3):
            pass
    except psycopg.OperationalError as error:
        pytest.skip(f"Postgres is not reachable, run 'make db-up' first. ({error})")

    name = f"pb_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

    try:
        yield make_conninfo(**{**parts, "dbname": name})
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def table_names(database_url: str) -> set[str]:
    """Return the names of every table in the public schema."""
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    return {str(name) for (name,) in rows}


@pytest.mark.database
def test_first_run_creates_the_schema(throwaway_database):
    applied = run_migrations(throwaway_database)

    assert applied == ["0001_initial.sql"]
    assert {"documents", "chunks", "chunk_embeddings"} <= table_names(throwaway_database)


@pytest.mark.database
def test_second_run_changes_nothing(throwaway_database):
    run_migrations(throwaway_database)

    assert run_migrations(throwaway_database) == []

    with psycopg.connect(throwaway_database) as conn:
        rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    assert [name for (name,) in rows] == ["0001_initial.sql"]


@pytest.mark.database
def test_a_document_chunk_and_embedding_round_trip(throwaway_database):
    run_migrations(throwaway_database)

    with psycopg.connect(throwaway_database) as conn:
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
def test_deleting_a_document_cascades(throwaway_database):
    run_migrations(throwaway_database)

    with psycopg.connect(throwaway_database) as conn:
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
def test_a_failing_migration_leaves_no_trace(throwaway_database, tmp_path):
    # 0002 creates a table and then contains invalid SQL. Both halves must be undone.
    shutil.copy(MIGRATIONS_DIR / "0001_initial.sql", tmp_path / "0001_initial.sql")
    write_migration(
        tmp_path,
        "0002_bad.sql",
        "CREATE TABLE half_created (id int);\nTHIS IS NOT SQL;\n",
    )

    with pytest.raises(psycopg.errors.SyntaxError):
        run_migrations(throwaway_database, tmp_path)

    assert "half_created" not in table_names(throwaway_database)
    with psycopg.connect(throwaway_database) as conn:
        rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    # 0001 ran in its own transaction and stands; 0002 left nothing behind.
    assert [name for (name,) in rows] == ["0001_initial.sql"]


@pytest.mark.database
def test_editing_an_applied_migration_is_refused(throwaway_database, tmp_path):
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    run_migrations(throwaway_database, tmp_path)

    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id bigint);\n")

    with pytest.raises(MigrationError, match="has changed since it was applied"):
        run_migrations(throwaway_database, tmp_path)


@pytest.mark.database
def test_an_unchanged_applied_migration_passes_the_check(throwaway_database, tmp_path):
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    run_migrations(throwaway_database, tmp_path)

    assert run_migrations(throwaway_database, tmp_path) == []


@pytest.mark.database
def test_a_migration_applied_but_missing_from_disk_is_tolerated(throwaway_database, tmp_path):
    # Happens legitimately on an older checkout, so it warns rather than failing.
    write_migration(tmp_path, "0001_first.sql", "CREATE TABLE example (id int);\n")
    write_migration(tmp_path, "0002_second.sql", "CREATE TABLE other (id int);\n")
    run_migrations(throwaway_database, tmp_path)

    (tmp_path / "0002_second.sql").unlink()

    assert run_migrations(throwaway_database, tmp_path) == []
