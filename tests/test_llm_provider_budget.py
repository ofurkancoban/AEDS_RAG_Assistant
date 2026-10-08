"""effective_daily_llm_budget's per-provider defaults (config.py) - each
provider's number matters for real reasons (the observed free-tier cap), so
a regression here would silently change how soon the assistant refuses new
requests for the active provider."""

from config import settings


def test_ollama_is_unmetered(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    assert settings.effective_daily_llm_budget == 0


def test_gemini_default_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    assert settings.effective_daily_llm_budget == 450


def test_openrouter_default_budget_matches_the_1000_request_tier(monkeypatch):
    """900, under the account's 1000/day free-model cap - see
    config.daily_budget_for_provider for why not the 50/day tier's 45."""
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    assert settings.effective_daily_llm_budget == 900


def test_explicit_budget_overrides_every_provider_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "daily_llm_call_budget", 999)
    assert settings.effective_daily_llm_budget == 999
