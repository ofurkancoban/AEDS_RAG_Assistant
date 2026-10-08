"""Personal progress messages and small talk never enter or come out of
the reviewed-answer cache."""

import pytest

from db import semantic_cache


@pytest.mark.parametrize("message, reusable", [
    ("How many times can I retake a failed exam?", True),
    ("My ECTS Tracker progress (60/120 ECTS completed): Economics (18/36 ECTS) - completed: wir821", False),
    ("hi", False),
    ("Thanks, that's helpful.", False),
])
def test_reusable_questions(message, reusable):
    assert semantic_cache.is_reusable_question(message) is reusable
