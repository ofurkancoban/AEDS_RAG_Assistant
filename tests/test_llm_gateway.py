"""The OpenRouter client can be pointed at another gateway for evaluation,
without ever sending the OpenRouter key there."""

import pytest

from config import settings
from graph import nodes


@pytest.fixture(autouse=True)
def _fresh_clients():
    nodes._get_openrouter_llm_cached.cache_clear()
    nodes._gateway_rate_limiter.cache_clear()
    yield
    nodes._get_openrouter_llm_cached.cache_clear()
    nodes._gateway_rate_limiter.cache_clear()


def test_production_default_is_openrouter_with_its_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-secret")
    llm = nodes._get_openrouter_llm_cached("some/model:free")
    assert str(llm.openai_api_base).rstrip("/") == nodes.OPENROUTER_BASE_URL
    assert llm.openai_api_key.get_secret_value() == "sk-or-secret"
    assert llm.rate_limiter is None


def test_another_gateway_never_receives_the_openrouter_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-secret")
    monkeypatch.setattr(settings, "openrouter_base_url", "https://api.kilo.ai/api/gateway")
    llm = nodes._get_openrouter_llm_cached("some/model:free")
    assert llm.openai_api_key.get_secret_value() != "sk-or-secret"


def test_hourly_cap_paces_calls(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_requests_per_hour", 180)
    llm = nodes._get_openrouter_llm_cached("some/model:free")
    assert llm.rate_limiter is not None
    assert llm.rate_limiter.requests_per_second == pytest.approx(0.05)
