"""The pipeline mirrors a content directory into the database, redoing only what changed."""

import pytest

from portfolio_bot.ingest.chunker import Chunk
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.ingest.pipeline import embedding_text, ingest

pytestmark = pytest.mark.database

ABOUT = "---\ntitle: About\n---\n\n## Background\n\nI studied CS.\n\n## Goals\n\nBackend work.\n"
PROJECT = "---\ntitle: Project\n---\n\n## Problem\n\nStudents needed reviews.\n"


@pytest.fixture
def content(tmp_path):
    (tmp_path / "about.md").write_text(ABOUT)
    (tmp_path / "project.md").write_text(PROJECT)
    return tmp_path


def run(db, root, embedder=None, **kwargs):
    return ingest(db, root, embedder or FakeEmbedder(), chunk_size=1000, chunk_overlap=0, **kwargs)


def count(db, table):
    return db.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def test_first_run_writes_every_document_with_one_embedding_per_chunk(db, content):
    report = run(db, content)

    assert report.processed == ["about.md", "project.md"]
    assert report.chunks_written == 3
    assert report.chunks_embedded == 3
    assert count(db, "documents") == 2
    assert count(db, "chunks") == 3
    assert count(db, "chunk_embeddings") == 3


def test_stored_chunks_point_back_into_the_file(db, content):
    run(db, content)

    rows = db.execute(
        """
        SELECT c.text, c.heading_path, c.char_start, c.char_end, c.token_count, d.title
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.source_path = 'about.md' ORDER BY c.ordinal
        """
    ).fetchall()

    assert [r["heading_path"] for r in rows] == [["Background"], ["Goals"]]
    for row in rows:
        assert ABOUT[row["char_start"] : row["char_end"]] == row["text"]
        assert row["title"] == "About"
        assert row["token_count"] > 0


def test_second_run_reprocesses_nothing(db, content):
    run(db, content)
    report = run(db, content)

    assert report.processed == []
    assert report.unchanged == ["about.md", "project.md"]
    assert count(db, "chunks") == 3


def test_editing_one_file_reprocesses_exactly_that_file(db, content):
    run(db, content)
    (content / "project.md").write_text(PROJECT + "\n## Result\n\nIt shipped.\n")

    report = run(db, content)

    assert report.processed == ["project.md"]
    assert report.unchanged == ["about.md"]
    assert count(db, "chunks") == 4
    assert count(db, "chunk_embeddings") == 4


def test_a_deleted_file_takes_its_chunks_and_embeddings_with_it(db, content):
    run(db, content)
    (content / "project.md").unlink()

    report = run(db, content)

    assert report.deleted == ["project.md"]
    assert count(db, "documents") == 1
    assert count(db, "chunks") == 2
    assert count(db, "chunk_embeddings") == 2


def test_force_reprocesses_unchanged_files(db, content):
    run(db, content)
    report = run(db, content, force=True)

    assert report.processed == ["about.md", "project.md"]
    assert count(db, "chunks") == 3


def test_a_different_embedding_model_reembeds_everything(db, content):
    run(db, content)
    report = run(db, content, embedder=FakeEmbedder(model_name="fake", model_revision="1"))

    assert report.processed == ["about.md", "project.md"]
    revisions = db.execute("SELECT DISTINCT model_revision FROM chunk_embeddings").fetchall()
    assert [r["model_revision"] for r in revisions] == ["1"]


def test_dry_run_reports_without_writing(db, content):
    report = run(db, content, dry_run=True)

    assert report.processed == ["about.md", "project.md"]
    assert report.chunks_written == 3
    assert report.chunks_embedded == 0
    assert count(db, "documents") == 0


def test_dry_run_reports_deletions_without_deleting(db, content):
    run(db, content)
    (content / "project.md").unlink()

    report = run(db, content, dry_run=True)

    assert report.deleted == ["project.md"]
    assert count(db, "documents") == 2


def test_a_broken_file_fails_alone_and_keeps_its_previous_version(db, content):
    run(db, content)
    (content / "project.md").write_text("no front matter any more\n")
    (content / "about.md").write_text(ABOUT + "\nMore.\n")

    report = run(db, content)

    assert [path for path, _ in report.failed] == ["project.md"]
    assert report.processed == ["about.md"]
    assert report.deleted == []
    assert count(db, "documents") == 2


def test_embedding_text_leads_with_the_document_and_headings():
    chunk = Chunk(ordinal=0, text="Body.", heading_path=("A", "B"), char_start=0, char_end=5)
    assert embedding_text("Title", chunk) == "Title > A > B\n\nBody."
