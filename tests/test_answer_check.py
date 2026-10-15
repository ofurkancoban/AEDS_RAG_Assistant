"""graph/answer_check.py: the background statement check of a generated
answer, and where its findings show up (/review, the weekly summary)."""

import json
from datetime import datetime, timezone

from config import settings
from graph import answer_check


def test_findings_are_read_from_the_json_reply():
    reply = 'Sure. {"unsupported": ["230,80 EUR as the fee - it is the ticket share only"]}'
    assert answer_check.parse_findings(reply) == ["230,80 EUR as the fee - it is the ticket share only"]
    assert answer_check.parse_findings('{"unsupported": []}') == []
    assert answer_check.parse_findings("I could not decide.") is None


def test_a_check_is_stored_and_found_again_by_question(monkeypatch):
    monkeypatch.setattr(answer_check, "check_answer", lambda q, c, a: ["15-20 Seiten - superseded value"])
    answer_check._run("Wie lang ist eine Hausarbeit?", "context", "15-20 Seiten")
    assert answer_check.latest_findings("wie lang ist eine hausarbeit?") == ["15-20 Seiten - superseded value"]


def test_an_unparseable_reply_records_nothing(monkeypatch):
    monkeypatch.setattr(answer_check, "check_answer", lambda q, c, a: None)
    answer_check._run("A question never checked before?", "context", "answer")
    assert answer_check.latest_findings("A question never checked before?") is None


def test_off_starts_no_check(monkeypatch):
    started = []
    monkeypatch.setattr(settings, "answer_check", "off")
    monkeypatch.setattr(answer_check.threading, "Thread", lambda **kw: started.append(kw))
    answer_check.check_in_background("q", "c", "a")
    assert started == []


def test_review_shows_the_findings(monkeypatch):
    from api import telegram_bot
    from db.models import AnswerStatus, CachedAnswer, SessionLocal
    from db.semantic_cache import _normalize

    question = "How much is the semester fee in total?"
    session = SessionLocal()
    try:
        session.add(CachedAnswer(question=question, question_normalized=_normalize(question), embedding="[]",
                                 answer="230.80 EUR", status=AnswerStatus.PENDING, sources_json="[]"))
        session.commit()
    finally:
        session.close()
    answer_check.record(question, "230.80 EUR", ["230.80 EUR - one component, not the total"])

    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, markup=None, chat_id=None: sent.append(text))
    telegram_bot._start_review("chat-check")
    shown = [t for t in sent if question in t]
    assert shown and "one component, not the total" in shown[-1]


def test_weekly_summary_counts_flagged_answers(monkeypatch):
    import scripts.check_contradictions as cc
    from db.models import AnswerCheck, SessionLocal
    from scripts.weekly_report import build_report

    monkeypatch.setattr(cc, "_documents", lambda: {})
    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        session.add_all([
            AnswerCheck(question="Fee?", question_normalized="fee?", answer="a", findings_json=json.dumps(["x - y"]), created_at=now),
            AnswerCheck(question="Ticket?", question_normalized="ticket?", answer="b", findings_json="[]", created_at=now),
        ])
        session.commit()
    finally:
        session.close()
    report = build_report(now)
    assert "Answer check:" in report and "had unsupported statements" in report
