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
