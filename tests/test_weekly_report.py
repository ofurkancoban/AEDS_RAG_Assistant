"""The weekly summary counts the week's questions and lists what went unanswered."""

from datetime import datetime, timedelta, timezone

from db.models import QueryLog, SessionLocal
from scripts.weekly_report import build_report


def test_report_counts_the_week(monkeypatch):
    import scripts.check_contradictions as cc

    monkeypatch.setattr(cc, "_documents", lambda: {})
    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        session.add_all([
            QueryLog(question="Where is the canteen?", thread_id="t1", answered=False, rating=-1, created_at=now - timedelta(days=1)),
            QueryLog(question="Where is the canteen?", thread_id="t2", answered=False, created_at=now - timedelta(days=2)),
            QueryLog(question="How many ECTS?", thread_id="t3", answered=True, rating=1, created_at=now - timedelta(days=3)),
            QueryLog(question="Old question", thread_id="t4", answered=False, created_at=now - timedelta(days=20)),
        ])
        session.commit()
    finally:
        session.close()

    report = build_report(now)
    assert "Questions: 3 (3 conversations)" in report
    assert "Not answered from the documents: 2" in report
    assert "Where is the canteen? (2x)" in report
    assert "1 helpful, 1 unhelpful" in report
    assert "Old question" not in report


def test_report_gives_answer_time_first_word_and_router_cache(monkeypatch, tmp_path):
    import json

    import scripts.check_contradictions as cc
    import scripts.export_review_cases as erc

    monkeypatch.setattr(cc, "_documents", lambda: {})
    monkeypatch.setattr(erc, "DRAFTS_PATH", tmp_path / "case_drafts.json")
    (tmp_path / "case_drafts.json").write_text(json.dumps([{"id": "downvoted-1", "needs_review": True}]))
    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        for i, (total, first, route_key) in enumerate([(8000, 3000, "route"), (12000, 5000, "route_cached")]):
            session.add(QueryLog(
                question=f"q{i}", thread_id=f"lat{i}", latency_ms=total, created_at=now - timedelta(hours=1),
                node_latencies_json=json.dumps({"retrieve": 2000, route_key: 900, "first_token": first}),
            ))
        session.add(QueryLog(question="cached", thread_id="c", latency_ms=50, served_from_cache=True, created_at=now))
        session.commit()
    finally:
        session.close()

    report = build_report(now)
    assert "Answer time: p50 12.0s, p95 12.0s (2 fresh answers)" in report
    assert "First word on screen: p50 5.0s" in report
    assert "Routing: 1 of 2 from cache, otherwise p50 0.9s" in report
    assert "Test case drafts to trim: 1" in report
