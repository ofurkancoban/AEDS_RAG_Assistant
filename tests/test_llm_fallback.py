"""graph/nodes.py's _with_fallback: whether it actually adds
openrouter_fallback_model as a LangChain fallback, and stays a no-op exactly
when it should. Added after a live test caught two real bugs this wiring
allowed (no client timeout, and an untested fallback model default that
turned out to be rate-limited) - these are the fast, no-network regression
tests that should have existed before that live test was the only check."""

from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.fallbacks import RunnableWithFallbacks

from config import settings
from graph.nodes import _with_fallback
from runtime_config import update_runtime_config

_DUMMY = RunnableLambda(lambda x: x)


def _reset(**fields):
    update_runtime_config(**fields)


def test_no_fallback_when_provider_is_not_openrouter():
    _reset(llm_provider="ollama", openrouter_model="a/a", openrouter_fallback_model="b/b")
    assert _with_fallback(_DUMMY) is _DUMMY


def test_no_fallback_when_fallback_model_is_empty():
    _reset(llm_provider="openrouter", openrouter_model="a/a", openrouter_fallback_model="")
    assert _with_fallback(_DUMMY) is _DUMMY


def test_no_fallback_when_fallback_equals_primary():
    """Falling back to the exact same model would just repeat the same
    failure, so this is treated the same as no fallback configured."""
    _reset(llm_provider="openrouter", openrouter_model="a/a", openrouter_fallback_model="a/a")
    assert _with_fallback(_DUMMY) is _DUMMY


def test_fallback_applied_when_provider_is_openrouter_with_a_distinct_fallback(monkeypatch):
    # ChatOpenAI (the fallback client) validates that an api_key is present
    # at construction time - real locally (from .env), absent in CI, so this
    # must not depend on either and set its own.
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    _reset(llm_provider="openrouter", openrouter_model="a/a", openrouter_fallback_model="b/b")
    wrapped = _with_fallback(_DUMMY)
    assert isinstance(wrapped, RunnableWithFallbacks)
    assert wrapped.invoke("x") == "x"  # the primary, behind the withdrawal watch
    assert len(wrapped.fallbacks) == 1


def test_no_fallback_when_the_daily_budget_fallback_has_diverted_away_from_openrouter(monkeypatch):
    """_with_fallback checks llm_budget.effective_provider(), not the raw
    configured one - once the daily-budget fallback has moved this call to
    gemini, wrapping it in an openrouter fallback model would mix two
    unrelated providers' fallback mechanisms."""
    import llm_budget
    from db.models import ProviderDailyUsage, SessionLocal

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    _reset(
        llm_provider="openrouter",
        openrouter_model="a/a",
        openrouter_fallback_model="b/b",
        daily_budget_fallback_provider="gemini",
    )

    session = SessionLocal()
    try:
        session.add(ProviderDailyUsage(day=llm_budget._today(), provider="openrouter", call_count=900))
        session.commit()
    finally:
        session.close()

    assert llm_budget.effective_provider() == "gemini"
    assert _with_fallback(_DUMMY) is _DUMMY


class _Gone(Exception):
    status_code = 404


def test_a_withdrawn_primary_is_marked_and_then_skipped(monkeypatch):
    from graph import nodes

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(nodes, "_GONE_MODELS", {})
    alerts = []
    monkeypatch.setattr(nodes, "_mark_model_gone", lambda model, exc: (alerts.append(model), nodes._GONE_MODELS.__setitem__(model, nodes.time.time())))
    _reset(llm_provider="openrouter", openrouter_model="a/a", openrouter_fallback_model="b/b")

    def dead(_):
        raise _Gone("The requested model is currently unavailable.")

    wrapped = _with_fallback(RunnableLambda(dead))
    wrapped.fallbacks = [RunnableLambda(lambda x: "from fallback")]
    assert wrapped.invoke("q") == "from fallback"
    assert alerts == ["a/a"]

    # Next call: no attempt on the withdrawn model at all.
    direct = _with_fallback(RunnableLambda(dead))
    assert not isinstance(direct, RunnableWithFallbacks)


def test_a_marked_model_is_tried_again_after_the_ttl(monkeypatch):
    from graph import nodes

    monkeypatch.setattr(nodes, "_GONE_MODELS", {"a/a": nodes.time.time() - nodes._MODEL_GONE_TTL_S - 1})
    assert not nodes._model_is_gone("a/a")


def test_rate_limits_do_not_count_as_withdrawn():
    from graph import nodes

    class _Busy(Exception):
        status_code = 429

    assert not nodes._is_model_gone_error(_Busy("Rate limit exceeded: free-models-per-min"))
    assert nodes._is_model_gone_error(Exception("No endpoints found for apodex/apodex-1.1-mini:free"))
