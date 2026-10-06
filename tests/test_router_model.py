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
    monkeypatch.setattr(settings, "openrouter_router_model", "")
    llm, model = nodes.get_router_llm()
    assert model is None
    assert llm.model_name == get_runtime_config().openrouter_model


def test_router_model_falls_back_to_main_model(monkeypatch):
    monkeypatch.setattr(llm_budget, "effective_provider", lambda: "openrouter")
    config = get_runtime_config()
    monkeypatch.setattr(settings, "openrouter_router_model", config.openrouter_fallback_model)

    llm, model = nodes.get_router_llm()
    wrapped = nodes._with_fallback(llm, primary_model=model)

    assert llm.model_name == config.openrouter_fallback_model
    assert _fallback_model(wrapped) == config.openrouter_model


def test_other_calls_keep_their_fallback(monkeypatch):
    monkeypatch.setattr(llm_budget, "effective_provider", lambda: "openrouter")
    config = get_runtime_config()
    wrapped = nodes._with_fallback(nodes.get_classifier_llm())
    assert _fallback_model(wrapped) == config.openrouter_fallback_model
