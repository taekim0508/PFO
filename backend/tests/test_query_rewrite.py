"""The subject's name in a question becomes a pronoun before the question is embedded."""

import pytest

from portfolio_bot.retrieval.query import neutralize_subject

NAMES = ("Tae Kim", "Tae")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Where did Tae go to school?", "Where did he go to school?"),
        ("What was Tae's GPA?", "What was his GPA?"),
        ("What was Tae’s GPA?", "What was his GPA?"),  # a curly apostrophe, as phones type it
        ("Where did Tae Kim go to school?", "Where did he go to school?"),
        ("What was Tae Kim's GPA?", "What was his GPA?"),
        ("where did tae go to school", "where did he go to school"),
        ("TAE KIM", "he"),
        ("Tae  Kim's projects", "his projects"),  # any whitespace inside the name
        ("Tae, Tae, and Tae", "he, he, and he"),
        ("Tae.", "he."),
    ],
)
def test_replaces_every_form_of_the_name(question, expected):
    assert neutralize_subject(question, NAMES) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Where did he go to school?",
        "Where can I see the repos at github.com/taekim0508?",  # part of a longer word
        "Email taekim0508@gmail.com",
        "Is Kim on the team?",  # "Kim" alone is not one of the names
        "",
    ],
)
def test_leaves_anything_else_alone(question):
    assert neutralize_subject(question, NAMES) == question


def test_the_longer_form_wins_so_no_surname_is_left_behind():
    # Given shortest first on purpose; the order passed in must not matter.
    assert neutralize_subject("Tae Kim's degree", ("Tae", "Tae Kim")) == "his degree"


def test_no_names_means_no_change():
    assert neutralize_subject("Where did Tae go to school?", ()) == "Where did Tae go to school?"


def test_blank_names_are_ignored_rather_than_matching_everywhere():
    assert neutralize_subject("Where did Tae go?", ("", "  ")) == "Where did Tae go?"


def test_characters_special_to_regular_expressions_are_taken_literally():
    assert neutralize_subject("Ask A.B. or AxB", ("A.B.",)) == "Ask he or AxB"
