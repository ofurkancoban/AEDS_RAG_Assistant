"""scripts/source_refresh.py's text normalisation and significance
heuristics - the two pure functions the nightly source-change check is
built on. No network, no LLM: covers the diff logic itself."""

from scripts.source_refresh import (
    FETCH_FAILURE_ALERT_THRESHOLD,
    _diff_tokens,
    _is_significant_change,
    _normalise,
    decide_fetch_failure_alert,
)


def test_normalise_collapses_whitespace():
    assert _normalise("a  b\n\tc") == "a b c"


def test_normalise_strips_the_self_regenerating_created_on_stamp():
    """Found live: the module handbook PDF bakes today's date into its own
    title line on every server-side render ("... erstellt am 28.09.2026"),
    which otherwise made the nightly check report a "change" daily with
    nothing actually different in the curriculum content."""
    text = "Modulhandbuch AEDS Master-Studiengang erstellt am 28.09.2026 Inhaltsverzeichnis"
    assert "erstellt am" not in _normalise(text)
    assert "28.09.2026" not in _normalise(text)


def test_normalise_does_not_touch_an_unrelated_date():
    text = "Application deadline: 15.07.2026"
    assert "15.07.2026" in _normalise(text)


def test_a_real_date_change_is_always_significant():
    """The whole reason _is_significant_change treats any digit-bearing
    token as significant regardless of size - a one-word deadline change
    must never be suppressed by the word-count floor."""
    tokens = _diff_tokens("Deadline: 15 July", "Deadline: 16 July")
    assert _is_significant_change(tokens, old_word_count=100) is True


def test_a_tiny_wording_change_is_not_significant():
    tokens = _diff_tokens("This is a test sentence here.", "This is a test, sentence here.")
    assert _is_significant_change(tokens, old_word_count=100) is False


def test_a_large_wording_change_is_significant_even_without_digits():
    old = "one two three four five six seven eight nine ten"
    new = "eleven twelve thirteen fourteen fifteen six seven eight nine ten"
    tokens = _diff_tokens(old, new)
    assert _is_significant_change(tokens, old_word_count=10) is True


def test_a_single_failure_is_not_yet_an_alert():
    count, outcome = decide_fetch_failure_alert(0, succeeded=False)
    assert count == 1
    assert outcome is None


def test_reaching_the_threshold_alerts_exactly_once():
    count, outcome = decide_fetch_failure_alert(FETCH_FAILURE_ALERT_THRESHOLD - 1, succeeded=False)
    assert count == FETCH_FAILURE_ALERT_THRESHOLD
    assert outcome == "broken"


def test_failing_again_past_the_threshold_does_not_realert():
    count, outcome = decide_fetch_failure_alert(FETCH_FAILURE_ALERT_THRESHOLD, succeeded=False)
    assert count == FETCH_FAILURE_ALERT_THRESHOLD + 1
    assert outcome is None


def test_a_success_before_the_threshold_resets_silently():
    count, outcome = decide_fetch_failure_alert(1, succeeded=True)
    assert count == 0
    assert outcome is None


def test_a_success_after_the_threshold_reports_recovery():
    count, outcome = decide_fetch_failure_alert(FETCH_FAILURE_ALERT_THRESHOLD, succeeded=True)
    assert count == 0
    assert outcome == "recovered"
