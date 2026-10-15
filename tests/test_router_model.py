"""The tool router can run on its own OpenRouter model, with the main model
as its fallback; unset, it uses the main model as before."""

import llm_budget
from config import settings
from graph import nodes
from runtime_config import get_runtime_config


def _fallback_model(wrapped):
    return wrapped.fallbacks[0].model_name


def test_router_uses_main_model_when_unset(monkeypatch):
    monkeypatch.setattr(llm_budget, "effective_provider", lambda: "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_router_model", "")
    llm, model = nodes.get_router_llm()
    assert model is None
    assert llm.model_name == get_runtime_config().openrouter_model


def _models(monkeypatch, main, fallback, router):
    from runtime_config import update_runtime_config

    monkeypatch.setattr(llm_budget, "effective_provider", lambda: "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_router_model", router)
    update_runtime_config(llm_provider="openrouter", openrouter_model=main, openrouter_fallback_model=fallback)


def test_router_model_falls_back_to_main_model(monkeypatch):
    _models(monkeypatch, main="main/m", fallback="", router="router/r")

    llm, model = nodes.get_router_llm()
    wrapped = nodes._with_fallback(llm, primary_model=model)

    assert llm.model_name == "router/r"
    assert _fallback_model(wrapped) == "main/m"


def test_other_calls_keep_their_fallback(monkeypatch):
    _models(monkeypatch, main="main/m", fallback="second/s", router="")
    wrapped = nodes._with_fallback(nodes.get_classifier_llm())
    assert _fallback_model(wrapped) == "second/s"


def test_workers_ai_comes_after_the_openrouter_fallback(monkeypatch):
    _models(monkeypatch, main="main/m", fallback="second/s", router="")
    monkeypatch.setattr(settings, "cloudflare_account_id", "acct")
    monkeypatch.setattr(settings, "cloudflare_api_token", "token")
    nodes._get_workers_ai_llm_cached.cache_clear()

    wrapped = nodes._with_fallback(nodes.get_classifier_llm())

    assert [f.model_name for f in wrapped.fallbacks] == ["second/s", settings.workers_ai_model]
    assert "/accounts/acct/ai/v1" in str(wrapped.fallbacks[1].openai_api_base)
    nodes._get_workers_ai_llm_cached.cache_clear()


def test_with_no_second_openrouter_model_workers_ai_is_the_fallback(monkeypatch):
    _models(monkeypatch, main="main/m", fallback="", router="")
    monkeypatch.setattr(settings, "cloudflare_account_id", "acct")
    monkeypatch.setattr(settings, "cloudflare_api_token", "token")
    nodes._get_workers_ai_llm_cached.cache_clear()

    wrapped = nodes._with_fallback(nodes.get_classifier_llm())

    assert [f.model_name for f in wrapped.fallbacks] == [settings.workers_ai_model]
    nodes._get_workers_ai_llm_cached.cache_clear()


def test_workers_ai_daily_allocation_counts_as_a_daily_quota_error():
    assert nodes._is_daily_quota_error(Exception("AiError: you have used up your daily free allocation of 10,000 neurons"))
