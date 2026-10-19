"""The admin question log: every question with its answer, including the
ones the review queue never holds (widget questions, follow-ups)."""

import json
from datetime import datetime, timedelta, timezone

from db.models import AnswerCheck, ChatMessage, QueryLog, SessionLocal, User

WIDGET_Q = "My ECTS Tracker progress (48/120 ECTS completed):\nEconomics (18/36 ECTS)\n\nQuestion: who create you ?"


def _seed():
    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        user = User(email=f"student-{now.timestamp()}@example.org", hashed_password="x")
        session.add(user)
        session.flush()
        turns = [
            ("t-widget", "What is the thesis length?", "About 80 pages.", "https://ofurkancoban.github.io", True, None),
            ("t-widget", WIDGET_Q, "I was created by Anthropic.", "https://ofurkancoban.github.io", True, -1),
            ("t-site", "When is the deadline?", "15 July.", None, False, None),
        ]
        ids = []
        for i, (thread, question, answer, origin, answered, rating) in enumerate(turns):
            session.add(ChatMessage(thread_id=thread, user_id=user.id, role="user", content=question))
            session.add(ChatMessage(thread_id=thread, user_id=user.id, role="assistant", content=answer))
            row = QueryLog(question=question, thread_id=thread, user_id=user.id, origin=origin, answered=answered,
                           rating=rating, latency_ms=4000, created_at=now - timedelta(minutes=10 - i))
            session.add(row)
            session.flush()
            ids.append(row.id)
        session.add(AnswerCheck(question=WIDGET_Q, question_normalized="x", answer="I was created by Anthropic.",
                                findings_json=json.dumps(["created by Anthropic - not in the context"]),
                                created_at=now - timedelta(minutes=9)))
        session.commit()
        return ids
    finally:
        session.close()


def test_the_log_shows_widget_follow_ups_with_answer_and_findings(client, admin_headers):
    ids = _seed()
    page = client.get("/admin/question-log", headers=admin_headers, params={"days": 1}).json()
    by_id = {item["id"]: item for item in page["items"]}
    widget = by_id[ids[1]]
    assert widget["question"] == "who create you ?"  # the course list is not shown
    assert widget["source"] == "widget" and (widget["turn"], widget["turns"]) == (2, 2)
    assert widget["answer"] == "I was created by Anthropic." and widget["rating"] == -1
    assert widget["check_findings"] == ["created by Anthropic - not in the context"]
    site = by_id[ids[2]]
    assert site["source"] == "site" and site["answered"] is False and site["check_findings"] is None


def test_the_log_filters(client, admin_headers):
    ids = _seed()

    def ids_for(**params):
        return {i["id"] for i in client.get("/admin/question-log", headers=admin_headers, params={"days": 1, **params}).json()["items"]}

    assert ids[1] in ids_for(show="flagged") and ids[0] not in ids_for(show="flagged")
    assert ids[2] in ids_for(show="unanswered") and ids[1] not in ids_for(show="unanswered")
    assert ids[1] in ids_for(show="downvoted")
    assert ids[2] not in ids_for(source="widget")
    assert ids_for(search="thesis length") >= {ids[0]} and ids[2] not in ids_for(search="thesis length")


def test_the_log_is_admin_only(client):
    assert client.get("/admin/question-log").status_code in (401, 403)
