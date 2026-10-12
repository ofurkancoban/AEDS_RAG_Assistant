"""/review: pending answers one at a time, most-asked first, the next one
sent as soon as a decision is made."""

import json

from api import telegram_bot
from db.models import AnswerStatus, CachedAnswer, QueryLog, SessionLocal


def _answer(session, question, asked):
    from db.semantic_cache import _normalize

    row = CachedAnswer(
        question=question,
        question_normalized=_normalize(question),
        embedding="[]",
        answer=f"Answer to {question}",
        status=AnswerStatus.PENDING,
        sources_json=json.dumps([{"source_id": "AEDS_website_exams_faq"}]),
    )
    session.add(row)
    for i in range(asked):
        session.add(QueryLog(question=question, thread_id=f"{question}-{i}"))
    session.flush()
    return row.id


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, markup=None, chat_id=None: sent.append((text, markup)))
    return sent


def test_review_starts_with_the_most_asked_answer_and_moves_on(monkeypatch):
    session = SessionLocal()
    try:
        rare = _answer(session, "Is there parking?", asked=1)
        common = _answer(session, "When is the exam registration?", asked=5)
        session.commit()
    finally:
        session.close()
    sent = _capture(monkeypatch)

    telegram_bot._start_review("chat")
    text, markup = sent[-1]
    assert "When is the exam registration?" in text
    assert "asked 5x" in text and "2 pending" in text
    assert "Sources: AEDS_website_exams_faq" in text
    assert markup["inline_keyboard"][0][0]["callback_data"] == f"ra:{common}"

    assert telegram_bot._dispatch_action(f"ra:{common}", "chat") == "Approved."
    assert "Is there parking?" in sent[-1][0]

    assert telegram_bot._dispatch_action(f"rr:{rare}", "chat") == "Rejected."
    assert sent[-1][0].startswith("Review queue done")

    session = SessionLocal()
    try:
        assert session.get(CachedAnswer, common).status == AnswerStatus.APPROVED
        assert session.get(CachedAnswer, rare).status == AnswerStatus.REJECTED
    finally:
        session.close()


def test_skip_leaves_the_answer_pending_and_shows_the_next(monkeypatch):
    session = SessionLocal()
    try:
        first = _answer(session, "How many ECTS is the thesis?", asked=3)
        _answer(session, "Where is the library?", asked=1)
        session.commit()
    finally:
        session.close()
    sent = _capture(monkeypatch)

    telegram_bot._start_review("chat")
    assert telegram_bot._dispatch_action(f"rs:{first}", "chat") == "Skipped."
    assert "Where is the library?" in sent[-1][0]
    assert "1 skipped" in sent[-1][0]

    session = SessionLocal()
    try:
        assert session.get(CachedAnswer, first).status == AnswerStatus.PENDING
    finally:
        session.close()

    # A fresh /review forgets the skips.
    telegram_bot._start_review("chat")
    assert "How many ECTS is the thesis?" in sent[-1][0]
