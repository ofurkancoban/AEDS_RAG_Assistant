"""scripts/system_health_check.py's decide_action: the pure state-transition
logic behind disk/memory/load alerting - given a fresh reading and the last
known state, what (if anything) to alert, and what to persist next. Real
system reads (shutil.disk_usage, /proc/meminfo, os.getloadavg) are not
covered here, matching this project's convention for operational scripts
(see tests/test_export_review_cases.py's own note on this)."""

from datetime import datetime, timedelta, timezone

from scripts.system_health_check import decide_action

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def test_no_alert_when_under_threshold_and_never_breached_before():
    message, state = decide_action("disk", 50.0, 85.0, None, NOW)
    assert message is None
    assert state == {"is_breached": False, "last_alerted_at": None}


def test_alerts_on_a_fresh_breach():
    message, state = decide_action("disk", 90.0, 85.0, None, NOW)
    assert message is not None
    assert "disk" in message
    assert "90.0" in message
    assert state["is_breached"] is True
    assert state["last_alerted_at"] == NOW


def test_does_not_realert_within_the_cooldown():
    prior = {"is_breached": True, "last_alerted_at": NOW - timedelta(hours=1)}
    message, state = decide_action("disk", 92.0, 85.0, prior, NOW, cooldown_hours=6.0)
    assert message is None
    # last_alerted_at is preserved, not bumped, while still in cooldown.
    assert state["last_alerted_at"] == prior["last_alerted_at"]


def test_realerts_once_the_cooldown_has_elapsed():
    prior = {"is_breached": True, "last_alerted_at": NOW - timedelta(hours=7)}
    message, state = decide_action("disk", 92.0, 85.0, prior, NOW, cooldown_hours=6.0)
    assert message is not None
    assert state["last_alerted_at"] == NOW


def test_sends_a_recovery_message_once_back_under_threshold():
    prior = {"is_breached": True, "last_alerted_at": NOW - timedelta(hours=1)}
    message, state = decide_action("disk", 60.0, 85.0, prior, NOW)
    assert message is not None
    assert "recovered" in message
    assert state == {"is_breached": False, "last_alerted_at": None}


def test_no_message_when_staying_healthy_after_a_past_recovery():
    prior = {"is_breached": False, "last_alerted_at": None}
    message, state = decide_action("disk", 50.0, 85.0, prior, NOW)
    assert message is None
    assert state == {"is_breached": False, "last_alerted_at": None}


def test_exactly_at_threshold_counts_as_breached():
    message, state = decide_action("memory", 90.0, 90.0, None, NOW)
    assert message is not None
    assert state["is_breached"] is True
