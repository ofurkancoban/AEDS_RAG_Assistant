"""A thumbs-down tells the admins and moves the answer to the top of the
review queue, without changing its review status."""

import json

import pytest

from api import routes_chat, telegram_bot
from db.models import AnswerStatus, CachedAnswer, SessionLocal
from db.semantic_cache import _normalize


def _fake_stream(answer: str):
    def fake(thread_id, question, source_id_filter=None):
        yield ("token", {"text": answer})
        yield ("done", {
            "sources": [],
            "final_answer": answer,
            "retrieval": [],
            "node_latencies": {},
            "answered": True,
            "time_sensitive": False,
            "has_expired_deadline": False,
        })
        yield ("contribution", {"detected_contribution": None})
    return fake


def _ask(client, headers, monkeypatch, question, answer, thread_id=None) -> dict:
    monkeypatch.setattr(routes_chat, "stream_chat", _fake_stream(answer))
    response = client.post("/chat/stream", json={"message": question, "thread_id": thread_id}, headers=headers)
    done = [b for b in response.text.split("\n\n") if b.startswith("event: done")][0]
    return json.loads(done.split("data:", 1)[1])


def _add_cached(question: str, status: AnswerStatus = AnswerStatus.APPROVED) -> int:
    session = SessionLocal()
    try:
        row = CachedAnswer(
            question=question,
            question_normalized=_normalize(question),
            embedding="[]",
            answer="Some earlier answer.",
            status=status,
        )
        session.add(row)
        session.commit()
        return row.id
    finally:
        session.close()


@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "notify_downvoted_answer", lambda **kw: sent.append(kw))
    return sent


def test_downvote_flags_the_queued_answer_and_alerts_admins(
    client, guest_headers, admin_headers, monkeypatch, alerts
):
    older = _add_cached("When is the library open?")
    answer_id = _add_cached("How much is the semester fee?")
    done = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90.")

    client.post("/chat/feedback", json={"query_log_id": done["query_log_id"], "rating": -1}, headers=guest_headers)
    client.post("/chat/feedback", json={"query_log_id": done["query_log_id"], "rating": -1}, headers=guest_headers)

    answers = client.get("/admin/answers?status_filter=all", headers=admin_headers).json()
    assert answers[0]["id"] == answer_id
    assert answers[0]["flagged"] is True and answers[0]["downvotes"] == 1
    assert answers[0]["status"] == "approved"
    assert {a["id"] for a in answers} >= {older}
    assert [a["id"] for a in client.get("/admin/answers?status_filter=flagged", headers=admin_headers).json()] == [answer_id]
    assert len(alerts) == 1 and alerts[0]["answer_id"] == answer_id


def test_review_clears_the_flag(client, guest_headers, admin_headers, monkeypatch, alerts):
    answer_id = _add_cached("How much is the semester fee?")
    done = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90.")
    client.post("/chat/feedback", json={"query_log_id": done["query_log_id"], "rating": -1}, headers=guest_headers)

    client.post(f"/admin/answers/{answer_id}/approve", json={}, headers=admin_headers)

    assert client.get("/admin/answers?status_filter=flagged", headers=admin_headers).json() == []


def test_follow_up_downvote_alerts_with_its_own_answer_but_flags_nothing(
    client, guest_headers, admin_headers, monkeypatch, alerts
):
    # Pending, so it is never served: the stubbed stream writes no
    # checkpoint, which would otherwise make this follow-up look like a
    # thread's first question to the cache lookup.
    _add_cached("Why?", AnswerStatus.PENDING)
    first = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90.")
    follow_up = _ask(client, guest_headers, monkeypatch, "Why?", "Because of the ticket.", first["thread_id"])

    client.post("/chat/feedback", json={"query_log_id": follow_up["query_log_id"], "rating": -1}, headers=guest_headers)

    assert client.get("/admin/answers?status_filter=flagged", headers=admin_headers).json() == []
    assert alerts == [{"question": "Why?", "answer": "Because of the ticket.", "answer_id": None}]
