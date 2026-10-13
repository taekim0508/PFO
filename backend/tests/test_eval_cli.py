"""`pb eval` checks the set against the corpus, then scores strategies over real Postgres.

The corpus is two small files. The fake embedder gives dense no sense of meaning, so the
questions are chosen for lexical, whose ranking can be worked out by hand: each question
shares words with exactly one section.
"""

import psycopg
import pytest
from psycopg.rows import dict_row

from portfolio_bot.cli import build_parser, command_eval, main
from portfolio_bot.db.migrate import run_migrations
from portfolio_bot.evaluation.questions import EvalQuestion, EvalSetError, Section
from portfolio_bot.evaluation.runner import check_sections, evaluate
from portfolio_bot.ingest.embedder import FakeEmbedder
from portfolio_bot.ingest.pipeline import ingest
from portfolio_bot.retrieval.lexical import LexicalRetriever
from portfolio_bot.settings import get_settings

EDUCATION = (
    "---\ntitle: Education\n---\n\n## Degrees\n\nI graduated from Vanderbilt.\n\n"
    "## Courses\n\nI took databases.\n"
)
ABROADLY = "---\ntitle: Abroadly\n---\n\n## Search\n\nI built the search index.\n"

QUESTIONS = """
questions:
  - question: Where did he graduate?
    expected: education.md > Degrees
  - question: Who built the search index?
    expected: abroadly.md
  - question: What about zebras?
    expected: education.md > Courses
"""


def test_run_requires_a_strategy():
    assert main(["eval", "run"]) == 2


def test_reports_a_missing_file(tmp_path, capsys):
    args = build_parser().parse_args(["eval", "run", "--strategy", "lexical", "--file", "x"])

    assert command_eval(get_settings(), args, FakeEmbedder()) == 1
    assert "not found" in capsys.readouterr().err


def test_reports_an_empty_set_before_touching_the_database(tmp_path, capsys):
    path = tmp_path / "set.yaml"
    path.write_text("questions: []\n")
    args = build_parser().parse_args(["eval", "compare", "--file", str(path)])

    assert command_eval(get_settings(), args, FakeEmbedder()) == 1
    assert "No questions yet" in capsys.readouterr().err


@pytest.fixture
def corpus(empty_database, tmp_path, monkeypatch):
    run_migrations(empty_database)
    monkeypatch.setenv("DATABASE_URL", empty_database)
    get_settings.cache_clear()
    content = tmp_path / "content"
    content.mkdir()
    (content / "education.md").write_text(EDUCATION)
    (content / "abroadly.md").write_text(ABROADLY)
    with psycopg.connect(empty_database, row_factory=dict_row) as conn:
        ingest(conn, content, FakeEmbedder(), chunk_size=1000, chunk_overlap=0)
    questions = tmp_path / "set.yaml"
    questions.write_text(QUESTIONS)
    return empty_database, questions


def eval_cli(argv):
    return command_eval(get_settings(), build_parser().parse_args(["eval", *argv]), FakeEmbedder())


@pytest.mark.database
def test_sections_lists_what_the_file_can_name(corpus, capsys):
    assert eval_cli(["sections"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "abroadly.md > Search",
        "education.md > Courses",
        "education.md > Degrees",
    ]


@pytest.mark.database
def test_scores_lexical_question_by_question(corpus, capsys):
    _, questions = corpus

    assert eval_cli(["run", "--strategy", "lexical", "--k", "2", "--file", str(questions)]) == 0

    # Graduate and search each match one chunk, first. Zebras match nothing.
    #   recall     (1 + 1 + 0) / 3
    #   MRR        (1 + 1 + 0) / 3
    #   precision  (1/2 + 1/2 + 0) / 3
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "lexical, k=2, 3 questions"
    assert [line.split()[:2] for line in out[2:5]] == [
        ["rank", "1"],
        ["rank", "1"],
        ["miss", "What"],
    ]
    assert out[-1].split() == ["recall@2", "0.667", "MRR", "0.667", "precision@2", "0.333"]


@pytest.mark.database
def test_compare_prints_a_row_per_strategy(corpus, capsys):
    _, questions = corpus

    assert eval_cli(["compare", "--file", str(questions)]) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "k=5, 3 questions"
    assert [line.split()[0] for line in out[3:]] == ["dense", "lexical", "hybrid"]


@pytest.mark.database
def test_refuses_a_section_the_corpus_does_not_have(corpus, tmp_path, capsys):
    path = tmp_path / "typo.yaml"
    path.write_text("questions:\n  - question: Q?\n    expected: education.md > Degreez\n")

    assert eval_cli(["compare", "--file", str(path)]) == 1

    err = capsys.readouterr().err
    assert "education.md > Degreez" in err
    assert "pb eval sections" in err


def test_check_sections_accepts_a_parent_of_a_stored_section():
    known = {Section("about.md", ("Background", "Early interest"))}

    check_sections([EvalQuestion("Q?", (Section("about.md", ("Background",)),))], known)
    with pytest.raises(EvalSetError):
        check_sections([EvalQuestion("Q?", (Section("about.md", ("Elsewhere",)),))], known)


@pytest.mark.database
def test_evaluate_cuts_results_to_k(db):
    document_id = db.execute(
        "INSERT INTO documents (source_path, title, content_hash) VALUES ('a.md', 'A', 'h') "
        "RETURNING id"
    ).fetchone()["id"]
    for ordinal in range(4):
        db.execute(
            "INSERT INTO chunks (document_id, ordinal, text, token_count, char_start, char_end) "
            "VALUES (%s, %s, 'a result', 1, 0, 1)",
            (document_id, ordinal),
        )

    report = evaluate(LexicalRetriever(db), [EvalQuestion("result", (Section("a.md"),))], k=3)

    assert report.results[0].retrieved == (Section("a.md"),) * 3
    assert report.precision == 1.0
