"""The evaluation file loads when well formed and names every problem when it is not."""

import pytest

from portfolio_bot.evaluation.questions import (
    EvalQuestion,
    EvalSetError,
    Section,
    load_questions,
    parse_section,
)
from portfolio_bot.settings import REPO_ROOT


def write(tmp_path, text):
    path = tmp_path / "set.yaml"
    path.write_text(text)
    return path


def test_loads_questions_with_one_or_several_sections(tmp_path):
    path = write(
        tmp_path,
        """
questions:
  - question: Where did Tae go to school?
    expected: education.md > Degrees and dates
    note: names Tae
  - question: What did he study?
    expected:
      - education.md > Degrees and dates
      - education.md > Relevant coursework
""",
    )

    assert load_questions(path) == [
        EvalQuestion(
            "Where did Tae go to school?",
            (Section("education.md", ("Degrees and dates",)),),
            "names Tae",
        ),
        EvalQuestion(
            "What did he study?",
            (
                Section("education.md", ("Degrees and dates",)),
                Section("education.md", ("Relevant coursework",)),
            ),
        ),
    ]


def test_the_committed_question_set_loads_and_meets_the_roadmap_minimum():
    assert len(load_questions(REPO_ROOT / "eval" / "retrieval.yaml")) >= 30


def test_reports_every_problem_at_once_naming_each_entry(tmp_path):
    path = write(
        tmp_path,
        """
questions:
  - expected: education.md
  - question: No answer given
  - question: Bad section
    expected: Degrees and dates
  - question: Twice
    expected: education.md
  - question: Twice
    expected: education.md
""",
    )

    with pytest.raises(EvalSetError) as raised:
        load_questions(path)

    message = str(raised.value)
    assert "entry 1: 'question' is missing" in message
    assert "'No answer given'): 'expected' needs at least one section" in message
    assert "'Bad section'): section 'Degrees and dates'" in message
    assert "entry 5 ('Twice'): duplicate question" in message


@pytest.mark.parametrize("text", ["not: [valid", "- just a list", "questions: nope"])
def test_refuses_a_file_without_a_questions_list(tmp_path, text):
    with pytest.raises(EvalSetError):
        load_questions(write(tmp_path, text))


def test_parses_a_section_and_prints_it_back():
    section = parse_section("about.md >  Background > Early interest ")

    assert section == Section("about.md", ("Background", "Early interest"))
    assert str(section) == "about.md > Background > Early interest"


@pytest.mark.parametrize("text", ["Background", "about.md > ", "about.md >> Background"])
def test_refuses_a_malformed_section(text):
    with pytest.raises(EvalSetError):
        parse_section(text)
