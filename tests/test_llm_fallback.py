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
    assert wrapped.runnable is _DUMMY
    assert len(wrapped.fallbacks) == 1
