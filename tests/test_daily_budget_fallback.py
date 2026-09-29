"""llm_budget.effective_provider(): falling back to a second provider once
the live one's own daily budget is exhausted, instead of refusing every new
question outright. See config.py's daily_budget_fallback_provider and
graph/nodes.py's get_llm/get_classifier_llm/_with_fallback/_with_resilience,
all of which read this rather than the raw configured provider."""

import llm_budget
from config import settings
from db.models import DailyLlmUsage, SessionLocal
from runtime_config import update_runtime_config


def _set_usage(count: int) -> None:
    session = SessionLocal()
    try:
        day = llm_budget._today()
        row = session.get(DailyLlmUsage, day)
        if row is None:
            session.add(DailyLlmUsage(day=day, call_count=count))
        else:
            row.call_count = count
        session.commit()
    finally:
        session.close()


def _reset(**fields):
    update_runtime_config(**fields)
    llm_budget._notified_fallback_day = None


def test_returns_the_live_provider_when_it_still_has_headroom(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(10)  # well under openrouter's 45

    assert llm_budget.effective_provider() == "openrouter"


def test_falls_back_once_the_live_provider_is_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(45)  # at openrouter's ceiling, gemini's (450) still has room

    assert llm_budget.effective_provider() == "gemini"


def test_no_fallback_configured_just_stays_on_the_exhausted_provider(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="")
    _set_usage(45)

    assert llm_budget.effective_provider() == "openrouter"


def test_a_fallback_that_is_also_exhausted_does_not_take_over(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(450)  # past both openrouter's 45 and gemini's 450 ceilings

    assert llm_budget.effective_provider() == "openrouter"


def test_fallback_pointing_at_itself_is_a_no_op(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="openrouter")
    _set_usage(45)

    assert llm_budget.effective_provider() == "openrouter"


def test_has_headroom_follows_the_effective_not_the_raw_provider(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(45)  # openrouter alone would refuse; gemini has plenty of room

    assert llm_budget.has_headroom() is True


def test_admin_notified_once_per_day_not_once_per_call(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(45)

    calls = []
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda text, **k: calls.append(text))

    llm_budget.effective_provider()
    llm_budget.effective_provider()
    llm_budget.effective_provider()

    assert len(calls) == 1
    assert "openrouter" in calls[0]
    assert "gemini" in calls[0]


def test_a_fallback_engagement_is_recorded_once_per_day(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda *a, **k: None)
    _reset(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    _set_usage(45)

    llm_budget.effective_provider()
    llm_budget.effective_provider()  # same day - must not add a second row

    events = llm_budget.recent_fallback_events()
    assert len(events) == 1
    assert events[0]["from_provider"] == "openrouter"
    assert events[0]["to_provider"] == "gemini"
    assert events[0]["usage_at_switch"] == 45
    assert events[0]["day"] == llm_budget._today()


def test_recent_fallback_events_are_newest_first(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from db.models import BudgetFallbackEvent

    session = SessionLocal()
    try:
        session.add(BudgetFallbackEvent(
            day="2026-01-01", from_provider="openrouter", to_provider="gemini",
            usage_at_switch=45, created_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
        session.add(BudgetFallbackEvent(
            day="2026-01-02", from_provider="openrouter", to_provider="gemini",
            usage_at_switch=45, created_at=datetime.now(timezone.utc),
        ))
        session.commit()
    finally:
        session.close()

    events = llm_budget.recent_fallback_events()
    assert [e["day"] for e in events] == ["2026-01-02", "2026-01-01"]


def test_active_chat_model_reflects_the_fallback_not_the_configured_provider(monkeypatch):
    from runtime_config import active_chat_model

    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda *a, **k: None)
    _reset(
        llm_provider="openrouter",
        openrouter_model="stealth/space-bunny-alpha",
        gemini_model="gemini-3.1-flash-lite",
        daily_budget_fallback_provider="gemini",
    )
    _set_usage(45)

    assert active_chat_model() == "gemini-3.1-flash-lite"
