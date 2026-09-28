"""api/main.py's global exception handler: turns an unhandled error into a
500 response and a Telegram alert, rate-limited per (path, exception type) so
an outage that fails every request to one endpoint sends one alert, not one
per request.

Calls the handler directly with a hand-built Request rather than going
through TestClient(api.main.app) - that would run api.main's lifespan, which
scans the documents folder and loads the real embedding model, exactly what
tests/conftest.py's own `app` fixture exists to avoid.
"""

import asyncio

import pytest
from starlette.requests import Request

import api.main as main_module


def _request(path: str = "/chat", method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("test", 0),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _reset_alert_cooldowns():
    """Belt and suspenders: every test below also uses its own request path
    (see _handle's default arg pattern in each test), so no test's assertion
    actually depends on this running - a cooldown from a previous test can
    never collide with a different path's key regardless."""
    main_module._last_alert_at.clear()
    yield
    main_module._last_alert_at.clear()


def _handle(path: str, exc: Exception):
    return asyncio.run(main_module._handle_unexpected_error(_request(path), exc))


def test_unhandled_error_returns_a_generic_500(monkeypatch):
    monkeypatch.setattr("api.telegram_bot.send_message", lambda *a, **k: None)

    response = _handle("/path-a", RuntimeError("boom"))

    assert response.status_code == 500
    # Generic on purpose - an internal exception message (a stack trace, a
    # DB error, a provider's raw response) must never reach an API client.
    import json

    assert json.loads(response.body) == {"detail": "Internal server error"}


def test_unhandled_error_alerts_telegram_once(monkeypatch):
    calls = []
    monkeypatch.setattr("api.telegram_bot.send_message", lambda text, **k: calls.append(text))

    _handle("/path-b", RuntimeError("boom"))

    assert len(calls) == 1
    assert "/path-b" in calls[0]
    assert "RuntimeError" in calls[0]
    assert "boom" in calls[0]


def test_repeated_errors_on_the_same_endpoint_are_not_spammed(monkeypatch):
    calls = []
    monkeypatch.setattr("api.telegram_bot.send_message", lambda text, **k: calls.append(text))

    for _ in range(5):
        _handle("/path-c", RuntimeError("boom"))

    assert len(calls) == 1


def test_a_different_exception_type_on_the_same_path_alerts_again(monkeypatch):
    calls = []
    monkeypatch.setattr("api.telegram_bot.send_message", lambda text, **k: calls.append(text))

    _handle("/path-d", RuntimeError("boom"))
    _handle("/path-d", ValueError("different failure"))

    assert len(calls) == 2


def test_a_failed_telegram_send_does_not_break_the_response(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("telegram unreachable")

    monkeypatch.setattr("api.telegram_bot.send_message", _raise)

    response = _handle("/path-e", RuntimeError("boom"))

    assert response.status_code == 500
