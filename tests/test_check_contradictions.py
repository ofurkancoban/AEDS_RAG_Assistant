"""The contradiction check finds two documents giving different values for
the same fact, and stays quiet when they agree."""

from scripts.check_contradictions import find_conflicts, normalize


def test_different_values_for_one_fact_are_reported():
    texts = {
        "regulations.pdf": "The Master's thesis must be assessed by the appointed examiners within six weeks of submission.",
        "faq.md": "### How long does grading take? Assessment happens expeditiously; typically within about eight weeks.",
    }
    conflicts = find_conflicts(texts)
    assert set(conflicts["thesis grading time (weeks)"]) == {"6", "8"}


def test_the_same_value_written_differently_is_not_a_conflict():
    texts = {
        "a.md": "Regular students pay EUR 457.90, made up of the following.",
        "b.md": "Regular students and international degree students pay EUR 457,90 in total.",
    }
    assert find_conflicts(texts) == {}


def test_number_words_normalize():
    assert normalize("six") == normalize("6") == "6"
    assert normalize("11,904") == normalize("11.904") == "11904"
