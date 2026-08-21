"""Apply numbered .sql migrations to Postgres, once each, in order.

The runner knows nothing about the schema. It finds files, works out which ones the
database has not seen, and applies those. All knowledge of what the tables look like lives
in the .sql files themselves, so a schema change is a new file and never a code change.

Each migration is applied inside a transaction that also records it as applied. The two
cannot disagree: a migration that fails partway through leaves no bookkeeping row and no
half-created tables, so the next run retries it from the beginning.

This module opens its own connection rather than using the pool. A pool exists to amortize
connection setup across many short concurrent requests; a migration run is a single
sequential job, and it has to work before the application is wired up at all.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from portfolio_bot.logging_config import get_logger

logger = get_logger(__name__)

# Resolved from this file rather than the working directory, so that `pb migrate` from
# backend/ and `make migrate` from the repository root find the same files.
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

# NNNN_lower_snake_case.sql. Enforced rather than assumed: a file that does not match is
# almost always a typo, and silently skipping it would apply an incomplete schema.
MIGRATION_FILENAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

# Created by the runner itself, not by a migration, because it has to exist before the
# runner can ask which migrations have run. checksum is what detects an edit to a file
# that has already been applied.
CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text        PRIMARY KEY,
    checksum   text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    """A migration could not be applied, or the migrations on disk are inconsistent."""


@dataclass(frozen=True)
class Migration:
    """One migration file, read from disk."""

    number: int
    filename: str
    path: Path
    sql: str
    checksum: str


def checksum(sql: str) -> str:
    """Return the SHA-256 hex digest of a migration's contents."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Read every migration in `directory`, sorted by numeric prefix.

    Sorting is on the parsed integer, not the filename, so that 0010 follows 0002 instead
    of preceding it as it would in a plain alphabetical sort.

    Raises MigrationError on a filename that does not match the required pattern, and on
    two files claiming the same number, since neither has a defined order.
    """
    if not directory.is_dir():
        raise MigrationError(f"Migrations directory does not exist: {directory}")

    migrations: list[Migration] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue

        match = MIGRATION_FILENAME.match(path.name)
        if match is None:
            raise MigrationError(
                f"Migration filename does not match NNNN_lower_snake_case.sql: {path.name}"
            )

        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                number=int(match.group(1)),
                filename=path.name,
                path=path,
                sql=sql,
                checksum=checksum(sql),
            )
        )

    # Sorting on the parsed number rather than the filename. With the four-digit width the
    # pattern enforces the two agree, so this is what keeps the order correct if that width
    # ever changes rather than what makes it correct today.
    migrations.sort(key=lambda migration: migration.number)

    seen: dict[int, str] = {}
    for migration in migrations:
        if migration.number in seen:
            raise MigrationError(
                f"Two migrations share the number {migration.number:04d}: "
                f"{seen[migration.number]} and {migration.filename}"
            )
        seen[migration.number] = migration.filename

    return migrations


def ensure_migrations_table(conn: psycopg.Connection[tuple[object, ...]]) -> None:
    """Create the bookkeeping table if it is not already there."""
    with conn.transaction():
        conn.execute(CREATE_MIGRATIONS_TABLE)


def applied_migrations(conn: psycopg.Connection[tuple[object, ...]]) -> dict[str, str]:
    """Return the filename and recorded checksum of every migration already applied."""
    rows = conn.execute("SELECT filename, checksum FROM schema_migrations").fetchall()
    return {str(filename): str(recorded) for filename, recorded in rows}


def verify_applied(migrations: list[Migration], applied: dict[str, str]) -> None:
    """Check that no already-applied migration has been edited since it ran.

    Editing a committed migration is invisible on a database where it already ran and
    changes what a fresh database gets, so the two drift apart with nothing to show for it.
    Comparing checksums turns that into an error at the next run.

    A migration recorded as applied but missing from disk is only logged. It happens
    legitimately when checking out a commit older than the migration.
    """
    on_disk = {migration.filename: migration.checksum for migration in migrations}

    for filename, recorded in sorted(applied.items()):
        current = on_disk.get(filename)
        if current is None:
            # Not "filename": logging reserves that attribute on every LogRecord.
            logger.warning(
                "migration recorded as applied but not found on disk",
                extra={"migration": filename},
            )
            continue
        if current != recorded:
            raise MigrationError(
                f"{filename} has changed since it was applied. A committed migration is "
                f"history and cannot be edited; add a new numbered migration instead."
            )


def apply_migration(conn: psycopg.Connection[tuple[object, ...]], migration: Migration) -> None:
    """Apply one migration and record it, both inside a single transaction.

    Recording the migration in the same transaction that runs it is what makes a failure
    safe: the insert is rolled back along with whatever the SQL managed to do, so the
    migration stays pending rather than being marked done in a database it never finished
    changing.
    """
    with conn.transaction():
        conn.execute(migration.sql)
        conn.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
            (migration.filename, migration.checksum),
        )


def run_migrations(database_url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration and return the filenames applied, in order.

    An empty list means the database was already up to date. Raises MigrationError if the
    migrations on disk are inconsistent with each other or with what has been applied, and
    lets psycopg.OperationalError through when the database cannot be reached.
    """
    migrations = discover_migrations(directory)

    with psycopg.connect(database_url, autocommit=True) as conn:
        ensure_migrations_table(conn)
        applied = applied_migrations(conn)
        verify_applied(migrations, applied)

        pending = [m for m in migrations if m.filename not in applied]
        for migration in pending:
            logger.info("applying migration", extra={"migration": migration.filename})
            apply_migration(conn, migration)

    return [migration.filename for migration in pending]
