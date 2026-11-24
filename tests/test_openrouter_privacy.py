"""Every OpenRouter call asks for providers that neither store nor train on
the prompt, unless the setting is switched off."""

from config import settings
from graph import nodes


def test_calls_deny_data_collection_by_default():
    for purpose in ("generation", "classifier"):
        body = nodes._openrouter_extra_body(purpose)
        assert body["provider"] == {"data_collection": "deny"}
        assert body["reasoning"] == nodes._OPENROUTER_REASONING[purpose]


def test_setting_can_switch_it_off(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_deny_data_collection", False)
    assert "provider" not in nodes._openrouter_extra_body("generation")


def test_models_that_require_reasoning_answer_with_low_effort(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_reasoning_required_models", "a/needs-reasoning:free, b/other:free")
    assert nodes._openrouter_extra_body("generation", "a/needs-reasoning:free")["reasoning"] == {"effort": "low"}
    assert nodes._openrouter_extra_body("generation", "c/plain:free")["reasoning"] == {"enabled": False}
    assert nodes._openrouter_extra_body("classifier", "a/needs-reasoning:free")["reasoning"] == {"effort": "low"}


def _fallback_chain(monkeypatch, after_workers_ai: bool, primary_model=None):
    import llm_budget
    from langchain_core.runnables import RunnableLambda
    from runtime_config import update_runtime_config

    update_runtime_config(llm_provider="openrouter", openrouter_model=None, openrouter_fallback_model=None)
    monkeypatch.setattr(settings, "openrouter_fallback_after_workers_ai", after_workers_ai)
    monkeypatch.setattr(llm_budget, "effective_provider", lambda: "openrouter")
    monkeypatch.setattr(nodes, "_workers_ai_configured", lambda: True)
    monkeypatch.setattr(nodes, "_get_workers_ai_llm_cached", lambda: RunnableLambda(lambda x: "workers_ai"))
    monkeypatch.setattr(nodes, "_get_openrouter_llm_cached", lambda model, purpose="": RunnableLambda(lambda x, m=model: m))
    chain = nodes._with_fallback(RunnableLambda(lambda x: "primary"), primary_model=primary_model)
    return [f.invoke(None) for f in chain.fallbacks]


def test_the_weaker_fallback_model_runs_after_workers_ai(monkeypatch):
    assert _fallback_chain(monkeypatch, True) == ["workers_ai", settings.openrouter_fallback_model]
    assert _fallback_chain(monkeypatch, False) == [settings.openrouter_fallback_model, "workers_ai"]

