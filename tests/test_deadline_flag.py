"""graph/build_graph.py's _has_passed_deadline: the signal the chat UI uses
to show a "mentions a passed deadline" banner on an answer that bypassed
retrieval entirely (see its own docstring) and so has no `sources` for the
usual expired-source badge to attach to."""

from graph.build_graph import _has_passed_deadline
from ingestion.deadlines import DEADLINE_PASSED_MARKER


def test_true_when_the_marker_is_present():
    answer = f"Deadline: July 15, 2026\nStatus: This deadline {DEADLINE_PASSED_MARKER} - it was 75 days ago."
    assert _has_passed_deadline(answer) is True


def test_false_for_an_ordinary_answer():
    assert _has_passed_deadline("The deadline is July 15, 2026.") is False


def test_false_for_an_empty_answer():
    assert _has_passed_deadline("") is False
