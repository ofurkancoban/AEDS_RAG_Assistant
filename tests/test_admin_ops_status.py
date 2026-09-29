"""GET /admin/ops-status: the admin-panel view of two things that
previously only ever reached an admin via Telegram - each provider's LLM
usage against its own daily budget (llm_budget.py) and the VPS host
checks' current breach state (SystemHealthAlertState, written by
scripts/system_health_check.py). Auth gating is covered by the
parametrized sweep in test_api_admin.py."""

from datetime import datetime, timezone

from db.models import ProviderDailyUsage, SessionLocal, SystemHealthAlertState


def test_reports_usage_for_every_tracked_provider_even_with_no_data(client, admin_headers):
    response = client.get("/admin/ops-status", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    providers = {row["provider"] for row in body["provider_usage"]}
    assert providers == {"gemini", "openrouter", "ollama"}
    assert body["system_health"] == []


def test_reports_recorded_provider_usage(client, admin_headers):
    import llm_budget

    session = SessionLocal()
    try:
        session.add(ProviderDailyUsage(day=llm_budget._today(), provider="gemini", call_count=7))
        session.commit()
    finally:
        session.close()

    response = client.get("/admin/ops-status", headers=admin_headers)
    by_provider = {row["provider"]: row for row in response.json()["provider_usage"]}
    assert by_provider["gemini"]["usage_today"] == 7
    assert by_provider["openrouter"]["usage_today"] == 0


def test_reports_system_health_check_states(client, admin_headers):
    session = SessionLocal()
    try:
        session.add(
            SystemHealthAlertState(
                check_name="disk",
                is_breached=True,
                last_alerted_at=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.add(SystemHealthAlertState(check_name="memory", is_breached=False, last_alerted_at=None))
        session.commit()
    finally:
        session.close()

    response = client.get("/admin/ops-status", headers=admin_headers)
    by_check = {row["check_name"]: row for row in response.json()["system_health"]}
    assert by_check["disk"]["is_breached"] is True
    assert by_check["disk"]["last_alerted_at"] is not None
    assert by_check["memory"]["is_breached"] is False
    assert by_check["memory"]["last_alerted_at"] is None
