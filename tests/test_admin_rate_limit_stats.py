"""GET /admin/rate-limit-stats: how often each limiter (api/rate_limit.py)
has actually rejected a request, aggregated from RateLimitRejectionDaily.
Auth gating is covered by the parametrized sweep in test_api_admin.py."""

from datetime import datetime, timedelta, timezone

from db.models import RateLimitRejectionDaily, SessionLocal


def _seed(day: str, limiter_name: str, count: int):
    session = SessionLocal()
    try:
        session.add(RateLimitRejectionDaily(day=day, limiter_name=limiter_name, count=count))
        session.commit()
    finally:
        session.close()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_empty_when_nothing_has_been_rejected(client, admin_headers):
    response = client.get("/admin/rate-limit-stats", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["by_limiter"] == []


def test_sums_rejections_across_the_window_ranked_by_count(client, admin_headers):
    _seed(_today(), "chat", 10)
    _seed(_today(), "auth", 3)

    response = client.get("/admin/rate-limit-stats?days=7", headers=admin_headers)
    body = response.json()
    assert body["days"] == 7
    assert body["by_limiter"][0] == {"limiter_name": "chat", "total_rejections": 10}
    assert body["by_limiter"][1] == {"limiter_name": "auth", "total_rejections": 3}


def test_excludes_days_outside_the_window(client, admin_headers):
    old_day = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    _seed(old_day, "guest", 5)

    response = client.get("/admin/rate-limit-stats?days=7", headers=admin_headers)
    assert response.json()["by_limiter"] == []
