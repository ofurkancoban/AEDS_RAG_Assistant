"""GET /admin/node-latency-stats: where a live pipeline turn's time goes,
averaged over many turns via QueryLog.node_latencies_json. Auth gating is
covered by the parametrized sweep in test_api_admin.py."""

import json
from datetime import datetime, timedelta, timezone

from db.models import QueryLog, SessionLocal


def _seed_query(node_latencies=None, thread_id="t1", created_at=None):
    session = SessionLocal()
    try:
        session.add(
            QueryLog(
                question="q",
                thread_id=thread_id,
                node_latencies_json=json.dumps(node_latencies) if node_latencies else None,
                created_at=created_at or datetime.now(timezone.utc),
            )
        )
        session.commit()
    finally:
        session.close()


def test_empty_when_no_queries_have_node_latencies(client, admin_headers):
    _seed_query(node_latencies=None)  # a cache hit - nothing to report

    response = client.get("/admin/node-latency-stats", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_turns"] == 0
    assert body["by_node"] == []


def test_averages_latency_per_node_across_turns(client, admin_headers):
    _seed_query({"retrieve": 100.0, "generate": 500.0}, thread_id="t1")
    _seed_query({"retrieve": 200.0, "generate": 700.0}, thread_id="t2")

    response = client.get("/admin/node-latency-stats", headers=admin_headers)
    body = response.json()
    assert body["total_turns"] == 2

    by_node = {row["node_name"]: row for row in body["by_node"]}
    assert by_node["retrieve"]["avg_ms"] == 150.0
    assert by_node["retrieve"]["sample_count"] == 2
    assert by_node["generate"]["avg_ms"] == 600.0
    # generate dominates total time, so it must be ranked first.
    assert body["by_node"][0]["node_name"] == "generate"


def test_days_window_excludes_older_turns(client, admin_headers):
    old = datetime.now(timezone.utc) - timedelta(days=40)
    _seed_query({"retrieve": 100.0}, thread_id="t-old", created_at=old)
    _seed_query({"retrieve": 200.0}, thread_id="t-new")

    response = client.get("/admin/node-latency-stats?days=30", headers=admin_headers)
    body = response.json()
    assert body["total_turns"] == 1
    assert body["by_node"][0]["avg_ms"] == 200.0
