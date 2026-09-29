"""GET /admin/origin-stats: traffic breakdown by calling origin, built on the
origin tagging already recorded on QueryLog (see its docstring in
db/models.py). Auth gating for this path is covered by the parametrized
sweep in test_api_admin.py; this file is only the breakdown behavior."""

from db.models import QueryLog, SessionLocal


def _seed_query(origin, thread_id="t1"):
    session = SessionLocal()
    try:
        session.add(QueryLog(question="q", thread_id=thread_id, origin=origin))
        session.commit()
    finally:
        session.close()


def test_empty_when_no_queries_in_range(client, admin_headers):
    response = client.get("/admin/origin-stats", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_queries"] == 0
    assert body["by_origin"] == []


def test_groups_by_normalised_origin_and_reports_percentages(client, admin_headers):
    _seed_query("https://aeds-rag-assistant.ofurkan.co")
    _seed_query("https://aeds-rag-assistant.ofurkan.co:443")  # same host, different port
    _seed_query("telegram")
    _seed_query(None)

    response = client.get("/admin/origin-stats", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_queries"] == 4

    by_origin = {row["origin"]: row for row in body["by_origin"]}
    assert by_origin["aeds-rag-assistant.ofurkan.co"]["count"] == 2
    assert by_origin["aeds-rag-assistant.ofurkan.co"]["percent"] == 0.5
    assert by_origin["telegram"]["count"] == 1
    assert by_origin["direct/unknown"]["count"] == 1


def test_distinct_hosts_are_not_merged(client, admin_headers):
    _seed_query("https://main-site.example.com")
    _seed_query("https://ects-tracker.example.com")

    response = client.get("/admin/origin-stats", headers=admin_headers)
    by_origin = {row["origin"] for row in response.json()["by_origin"]}
    assert by_origin == {"main-site.example.com", "ects-tracker.example.com"}


def test_days_window_excludes_older_queries(client, admin_headers):
    from datetime import datetime, timedelta, timezone

    session = SessionLocal()
    try:
        old = QueryLog(
            question="old",
            thread_id="t2",
            origin="telegram",
            created_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        session.add(old)
        session.commit()
    finally:
        session.close()
    _seed_query("telegram")

    response = client.get("/admin/origin-stats?days=30", headers=admin_headers)
    body = response.json()
    assert body["total_queries"] == 1
