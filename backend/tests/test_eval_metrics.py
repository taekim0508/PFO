"""The three retrieval metrics, on hand-built result lists with hand-computed answers."""

import pytest

from portfolio_bot.evaluation.metrics import precision_at_k, recall_at_k, reciprocal_rank
from portfolio_bot.evaluation.questions import Section

EDU = Section("education.md", ("Degrees and dates",))
COURSES = Section("education.md", ("Relevant coursework",))
ABOUT = Section("about.md", ("Background",))
ABOUT_SUB = Section("about.md", ("Background", "Early interest"))
OTHER = Section("abroadly.md", ("Search",))


@pytest.mark.parametrize(
    ("retrieved", "expected_rr"),
    [
        ([EDU, OTHER, OTHER], 1.0),
        ([OTHER, OTHER, EDU], 1 / 3),
        ([OTHER, OTHER, OTHER], 0.0),
        ([], 0.0),
    ],
)
def test_reciprocal_rank_is_one_over_the_first_hit(retrieved, expected_rr):
    assert reciprocal_rank(retrieved, [EDU]) == expected_rr


def test_several_chunks_of_one_section_count_once_for_recall_and_each_for_precision():
    # Two chunks of the one expected section, then three misses.
    retrieved = [EDU, EDU, OTHER, OTHER, OTHER]

    assert recall_at_k(retrieved, [EDU]) == 1.0
    assert precision_at_k(retrieved, [EDU], k=5) == 2 / 5


def test_recall_is_the_share_of_expected_sections_found():
    retrieved = [OTHER, COURSES, OTHER]

    assert recall_at_k(retrieved, [EDU, COURSES]) == 0.5
    # The first relevant chunk is at rank 2, whichever expected section it belongs to.
    assert reciprocal_rank(retrieved, [EDU, COURSES]) == 0.5


def test_precision_divides_by_k_not_by_what_came_back():
    # Two right answers out of a possible five is 0.4, not 1.0.
    assert precision_at_k([EDU, EDU], [EDU], k=5) == 2 / 5


def test_a_section_covers_the_chunks_under_its_subheadings():
    assert reciprocal_rank([OTHER, ABOUT_SUB], [ABOUT]) == 0.5
    assert recall_at_k([ABOUT_SUB], [ABOUT]) == 1.0


def test_a_whole_file_covers_every_section_in_it():
    assert recall_at_k([COURSES], [Section("education.md")]) == 1.0


def test_a_subsection_does_not_cover_its_parent():
    # Expecting the narrower section, a chunk from the broader one is not the answer.
    assert reciprocal_rank([ABOUT], [ABOUT_SUB]) == 0.0
