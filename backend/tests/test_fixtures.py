"""Tests for the fixtures themselves.

A fixture that silently fails to isolate tests is worse than no fixture, because every test
that depends on it starts lying. These check the three claims conftest.py makes: the empty
database is empty, the migrated one has every migration, and `db` leaves nothing behind.
"""

from __future__ import annotations

import psycopg
import pytest

SAMPLE_DOCUMENT = "INSERT INTO documents (source_path, title, content_hash) VALUES (%s, 'T', 'h')"


@pytest.mark.database
def test_empty_database_really_is_empty(empty_database):
    with psycopg.connect(empty_database) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()

    assert rows == []


@pytest.mark.database
def test_migrated_database_has_every_migration_applied(migrated_database):
    with psycopg.connect(migrated_database) as conn:
        applied = conn.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename"
        ).fetchall()
        indexes = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename IN ('chunks', 'chunk_embeddings')"
        ).fetchall()

    assert [name for (name,) in applied] == ["0001_initial.sql", "0002_indexes.sql"]
    # 0002 in particular, since a fixture that stopped at 0001 would still look fine above.
    assert "chunk_embeddings_embedding_hnsw" in {name for (name,) in indexes}


@pytest.mark.database
def test_db_gives_a_working_connection_with_rows_keyed_by_column_name(db):
    row = db.execute("SELECT count(*) AS n FROM chunks").fetchone()

    assert row == {"n": 0}


@pytest.mark.database
def test_db_writes_are_never_committed(db, migrated_database):
    # The guarantee behind the rollback: the write is real for this connection and invisible
    # to every other one, because it is sitting in a transaction that will never commit.
    # This holds regardless of whether the test passes, which a plain connection cannot say.
    db.execute(SAMPLE_DOCUMENT, ("content/uncommitted.md",))
    assert db.execute("SELECT count(*) AS n FROM documents").fetchone() == {"n": 1}

    with psycopg.connect(migrated_database) as other:
        (count,) = other.execute("SELECT count(*) FROM documents").fetchone()

    assert count == 0


@pytest.mark.database
def test_db_leaves_nothing_behind_for_the_next_test(db):
    # Paired with the test above, which wrote a document into this same database. pytest runs
    # tests in file order, so if the rollback did not happen this would find that row.
    row = db.execute("SELECT count(*) AS n FROM documents").fetchone()

    assert row == {"n": 0}
