"""GET/PUT /admin/config: the live-switch surface (api/routes_admin.py) that
lets an admin change llm_provider, its model, and openrouter_fallback_model
without a restart. Previously this endpoint had no coverage beyond "a
non-admin cannot reach it" - every behavior here was only ever checked by
hand against a running server.

settings.gemini_api_key / settings.openrouter_api_key are monkeypatched
explicitly in every test that needs a key present, rather than relying on
whatever a local .env happens to hold - real key values there would make
these tests pass locally and fail (or silently test the wrong branch) in CI,
where no such .env exists.
"""

from config import settings


def test_get_config_reports_openrouter_fallback_model(client, admin_headers):
    response = client.get("/admin/config", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    # Compared against the settings rather than literal model names: the
    # defaults change whenever a free model is withdrawn or replaced.
    assert body["openrouter_model"]["value"] == settings.openrouter_model
    assert body["openrouter_fallback_model"]["value"] == settings.openrouter_fallback_model
    # Default provider is ollama (see conftest.py) - the openrouter fields
    # are stored but not in effect, so the UI must not offer to edit them.
    assert body["openrouter_model"]["read_only"] is True
    assert body["openrouter_fallback_model"]["read_only"] is True


def test_cannot_switch_to_a_provider_with_no_configured_key(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    response = client.put("/admin/config", headers=admin_headers, json={"llm_provider": "openrouter"})
    assert response.status_code == 400


def test_switching_provider_updates_the_active_chat_model(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    response = client.put(
        "/admin/config",
        headers=admin_headers,
        json={"llm_provider": "gemini", "gemini_model": "gemini-3.6-flash"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm_provider"]["value"] == "gemini"
    assert body["chat_model"]["value"] == "gemini-3.6-flash"
    # Now in effect, so gemini_model becomes editable and openrouter_model does not.
    assert body["gemini_model"]["read_only"] is False
    assert body["openrouter_model"]["read_only"] is True


def test_openrouter_model_not_editable_while_a_different_provider_is_active(client, admin_headers):
    response = client.put("/admin/config", headers=admin_headers, json={"openrouter_model": "x/y"})
    assert response.status_code == 400


def test_openrouter_fallback_model_can_be_cleared_but_openrouter_model_cannot(
    client, admin_headers, monkeypatch
):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    switch = client.put("/admin/config", headers=admin_headers, json={"llm_provider": "openrouter"})
    assert switch.status_code == 200

    cleared = client.put("/admin/config", headers=admin_headers, json={"openrouter_fallback_model": ""})
    assert cleared.status_code == 200
    assert cleared.json()["openrouter_fallback_model"]["value"] == ""

    emptied = client.put("/admin/config", headers=admin_headers, json={"openrouter_model": ""})
    assert emptied.status_code == 400


def test_rerank_top_k_cannot_exceed_retrieval_top_k(client, admin_headers):
    response = client.put(
        "/admin/config",
        headers=admin_headers,
        json={"retrieval_top_k": 5, "rerank_top_k": 8},
    )
    assert response.status_code == 400


def test_retrieval_top_k_out_of_bounds_is_rejected(client, admin_headers):
    response = client.put("/admin/config", headers=admin_headers, json={"retrieval_top_k": 999})
    assert response.status_code == 400


def test_system_prompt_override_can_be_set_and_reset(client, admin_headers):
    set_response = client.put(
        "/admin/config", headers=admin_headers, json={"system_prompt_override": "Be terse."}
    )
    assert set_response.status_code == 200
    assert set_response.json()["system_prompt_override"]["value"] == "Be terse."

    reset_response = client.put(
        "/admin/config", headers=admin_headers, json={"reset_system_prompt": True}
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["system_prompt_override"]["value"] is None


def test_daily_budget_fallback_provider_is_always_editable_regardless_of_live_provider(client, admin_headers, monkeypatch):
    # Unlike openrouter_model/openrouter_fallback_model, this applies no
    # matter which provider is currently live - the default fixture
    # provider is ollama (see conftest.py), and it must still be settable.
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    response = client.put(
        "/admin/config", headers=admin_headers, json={"daily_budget_fallback_provider": "gemini"}
    )
    assert response.status_code == 200
    assert response.json()["daily_budget_fallback_provider"]["value"] == "gemini"


def test_daily_budget_fallback_provider_rejects_an_unknown_name(client, admin_headers):
    response = client.put(
        "/admin/config", headers=admin_headers, json={"daily_budget_fallback_provider": "not-a-real-provider"}
    )
    assert response.status_code == 400


def test_daily_budget_fallback_provider_refuses_a_provider_with_no_configured_key(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    response = client.put(
        "/admin/config", headers=admin_headers, json={"daily_budget_fallback_provider": "gemini"}
    )
    assert response.status_code == 400


def test_daily_budget_fallback_provider_can_be_cleared(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    client.put("/admin/config", headers=admin_headers, json={"daily_budget_fallback_provider": "gemini"})

    response = client.put(
        "/admin/config", headers=admin_headers, json={"daily_budget_fallback_provider": ""}
    )
    assert response.status_code == 200
    assert response.json()["daily_budget_fallback_provider"]["value"] == ""


def test_effective_provider_matches_llm_provider_when_no_fallback_is_active(client, admin_headers):
    response = client.get("/admin/config", headers=admin_headers)
    body = response.json()
    assert body["effective_provider"]["value"] == body["llm_provider"]["value"]
    assert body["effective_provider"]["read_only"] is True


def test_effective_provider_reflects_an_active_budget_fallback(client, admin_headers, monkeypatch):
    import llm_budget
    from db.models import ProviderDailyUsage, SessionLocal

    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda *a, **k: None)

    client.put(
        "/admin/config",
        headers=admin_headers,
        json={"llm_provider": "openrouter", "daily_budget_fallback_provider": "gemini"},
    )

    session = SessionLocal()
    try:
        session.add(ProviderDailyUsage(day=llm_budget._today(), provider="openrouter", call_count=900))
        session.commit()
    finally:
        session.close()

    response = client.get("/admin/config", headers=admin_headers)
    body = response.json()
    assert body["llm_provider"]["value"] == "openrouter"
    assert body["effective_provider"]["value"] == "gemini"
    assert body["chat_model"]["value"] == body["gemini_model"]["value"]


def test_budget_fallback_events_endpoint_reports_recorded_switches(client, admin_headers, monkeypatch):
    import llm_budget
    from db.models import ProviderDailyUsage, SessionLocal

    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr("api.telegram_bot._notify_admins", lambda *a, **k: None)

    client.put(
        "/admin/config",
        headers=admin_headers,
        json={"llm_provider": "openrouter", "daily_budget_fallback_provider": "gemini"},
    )
    session = SessionLocal()
    try:
        session.add(ProviderDailyUsage(day=llm_budget._today(), provider="openrouter", call_count=900))
        session.commit()
    finally:
        session.close()

    llm_budget.effective_provider()  # triggers and records the fallback

    response = client.get("/admin/budget-fallback-events", headers=admin_headers)
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["from_provider"] == "openrouter"
    assert events[0]["to_provider"] == "gemini"
    assert events[0]["usage_at_switch"] == 900


def test_budget_fallback_events_endpoint_is_closed_to_visitors(client, guest_headers):
    response = client.get("/admin/budget-fallback-events", headers=guest_headers)
    assert response.status_code == 403
