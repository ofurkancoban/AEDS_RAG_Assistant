"""When the provider itself says its daily quota is spent, the call is not
retried for minutes: the provider is marked exhausted for the day, the
fallback provider answers the same call, and admins are told why."""

import pytest

import llm_budget
from config import settings
from graph import nodes
from runtime_config import update_runtime_config


class _ProviderError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


DAILY = _ProviderError(429, "Error code: 429 - Rate limit exceeded: free-models-per-day-high-balance.")
PER_MINUTE = _ProviderError(429, "Error code: 429 - Rate limit exceeded: free-models-per-min.")


class _Answers:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def invoke(self, input, config=None):
        self.calls += 1
        return self.text


class _Fails:
    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    def invoke(self, input, config=None):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "recovered"


@pytest.fixture
def openrouter_live(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    update_runtime_config(llm_provider="openrouter", daily_budget_fallback_provider="gemini")
    llm_budget._notified_fallback_day = None
    alerts = []
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda text, *a, **k: alerts.append(text))
    monkeypatch.setattr(nodes, "_retry_delay", lambda attempt: 0)
    return alerts


def test_daily_quota_switches_to_the_fallback_at_once(openrouter_live):
    failing = _Fails(DAILY, DAILY)
    fallback = _Answers("answer from gemini")

    result = nodes._with_resilience(failing, rebuild=lambda: fallback).invoke("q")

    assert result == "answer from gemini"
    assert failing.calls == 1  # not retried
    assert llm_budget.effective_provider() == "gemini"
    assert len(openrouter_live) == 1 and "reported its daily quota exhausted" in openrouter_live[0]


def test_the_switch_lasts_for_the_rest_of_the_day(openrouter_live):
    nodes._with_resilience(_Fails(DAILY), rebuild=lambda: _Answers("ok")).invoke("q")

    assert llm_budget.usage_today("openrouter") >= llm_budget.daily_budget("openrouter")
    assert llm_budget.effective_provider() == "gemini"


def test_per_minute_limits_are_still_retried(openrouter_live):
    failing = _Fails(PER_MINUTE, PER_MINUTE)

    result = nodes._with_resilience(failing, rebuild=lambda: _Answers("unused")).invoke("q")

    assert result == "recovered"
    assert failing.calls == 3
    assert llm_budget.effective_provider() == "openrouter"
    assert openrouter_live == []


def test_without_a_fallback_the_error_surfaces_instead_of_hanging(openrouter_live):
    update_runtime_config(daily_budget_fallback_provider="")
    failing = _Fails(DAILY)

    with pytest.raises(_ProviderError):
        nodes._with_resilience(failing, rebuild=lambda: _Answers("unused")).invoke("q")
    assert failing.calls == 1


@pytest.mark.parametrize(
    "error, expected",
    [
        (DAILY, True),
        (_ProviderError(429, "Quota exceeded for GenerateRequestsPerDayPerProjectPerModel"), True),
        (PER_MINUTE, False),
        (_ProviderError(500, "per-day"), False),
    ],
)
def test_daily_quota_errors_are_told_apart(error, expected):
    assert nodes._is_daily_quota_error(error) is expected
