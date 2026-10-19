"""db/reranker.py: the hosted reranker is used when configured, and any
failure falls back to the local model without failing the question."""

import httpx
from langchain_core.documents import Document

from config import settings
from db import reranker


class _Local:
    def __init__(self):
        self.calls = 0

    def predict(self, pairs):
        self.calls += 1
        return [0.1 * i for i in range(len(pairs))]


def _docs():
    return [Document(page_content=f"passage {i}", metadata={}) for i in range(3)]


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "cloudflare_account_id", "acct")
    monkeypatch.setattr(settings, "cloudflare_api_token", "token")
    monkeypatch.setattr(reranker, "_api_down_until", 0.0)
    local = _Local()
    monkeypatch.setattr(reranker, "get_reranker", lambda: local)
    return local


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_hosted_scores_decide_the_order(monkeypatch):
    local = _configure(monkeypatch)
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, auth=headers["Authorization"], body=json)
        # The API returns results best-first, with the passage index as id.
        return _Response({"result": {"response": [{"id": 0, "score": 0.9}, {"id": 2, "score": 0.5}, {"id": 1, "score": 0.1}]}})

    monkeypatch.setattr(httpx, "post", fake_post)
    ranked = reranker.rerank("q", _docs(), 2)

    assert [d.page_content for d in ranked] == ["passage 0", "passage 2"]
    assert ranked[0].metadata["_rerank_score"] == 0.9
    assert local.calls == 0
    assert "/accounts/acct/ai/run/@cf/baai/bge-reranker-base" in sent["url"]
    assert sent["auth"] == "Bearer token"
    assert sent["body"]["contexts"][1] == {"text": "passage 1"}


def test_a_failure_falls_back_and_backs_off(monkeypatch):
    local = _configure(monkeypatch)
    attempts = []

    def failing_post(*a, **kw):
        attempts.append(1)
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", failing_post)
    reranker.rerank("q", _docs(), 2)
    reranker.rerank("q", _docs(), 2)

    assert local.calls == 2
    # The first question retried the timeout once; the second did not wait
    # for the API at all.
    assert len(attempts) == 2


def test_unconfigured_means_local_only(monkeypatch):
    local = _configure(monkeypatch)
    monkeypatch.setattr(settings, "cloudflare_api_token", "")

    def no_network(*a, **kw):
        raise AssertionError("API called")

    monkeypatch.setattr(httpx, "post", no_network)
    reranker.rerank("q", _docs(), 2)
    assert local.calls == 1


def test_a_timeout_is_retried_once_before_falling_back(monkeypatch):
    local = _configure(monkeypatch)
    attempts = []

    def slow_then_fine(url, headers, json, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("The read operation timed out")
        return _Response({"result": {"response": [{"id": 0, "score": 0.9}, {"id": 1, "score": 0.5}, {"id": 2, "score": 0.1}]}})

    monkeypatch.setattr(httpx, "post", slow_then_fine)
    ranked = reranker.rerank("q", _docs(), 1)

    assert len(attempts) == 2
    assert local.calls == 0
    assert ranked[0].metadata["_rerank_score"] == 0.9


def test_a_used_up_daily_allocation_pauses_until_midnight_utc(monkeypatch):
    local = _configure(monkeypatch)
    attempts = []
    request = httpx.Request("POST", "https://api.cloudflare.com/x")
    body = '{"errors":[{"code":4006,"message":"you have used up your daily free allocation of 10,000 neurons"}]}'

    def used_up(*a, **kw):
        attempts.append(1)
        response = httpx.Response(429, text=body, request=request)
        raise httpx.HTTPStatusError("429", request=request, response=response)

    monkeypatch.setattr(httpx, "post", used_up)
    monkeypatch.setattr(reranker, "_seconds_to_utc_midnight", lambda: 5 * 3600.0)
    import time

    reranker.rerank("q", _docs(), 2)
    assert len(attempts) == 1 and local.calls == 1
    assert reranker._api_down_until - time.monotonic() > 4 * 3600


def test_other_rate_limits_keep_the_short_pause(monkeypatch):
    _configure(monkeypatch)
    request = httpx.Request("POST", "https://api.cloudflare.com/x")

    def busy(*a, **kw):
        raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, text="slow down", request=request))

    monkeypatch.setattr(httpx, "post", busy)
    import time

    reranker.rerank("q", _docs(), 2)
    assert reranker._api_down_until - time.monotonic() <= reranker._API_BACKOFF_S
