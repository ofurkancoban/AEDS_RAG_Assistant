"""New user-side Telegram features: /new (conversation reset) and 👍/👎
feedback. Mirrors tests/test_telegram_user_chat.py's stubbing approach."""

import pytest

from api import telegram_chat
from db.models import QueryLog, SessionLocal, User


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch):
    import graph.build_graph as build_graph

    def fake_run_chat(thread_id: str, question: str, source_id_filter=None):
        return {
            "answer": "Stubbed answer.",
            "sources": [{"source_id": "stub_source", "page": None, "url": None}],
            "retrieval": [],
            "node_latencies": {},
            "answered": True,
            "time_sensitive": False,
            "detected_contribution": None,
        }

    monkeypatch.setattr(build_graph, "run_chat", fake_run_chat)
    monkeypatch.setattr(build_graph, "is_cacheable_turn", lambda thread_id: False)
    yield


def _cleanup(chat_id: str) -> None:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == f"telegram-{chat_id}@aeds.local").first()
        if user is not None:
            session.query(QueryLog).filter(QueryLog.user_id == user.id).delete()
            session.delete(user)
            session.commit()
    finally:
        session.close()


def test_new_command_changes_the_thread_id():
    chat_id = "pytest_new_1"
    try:
        _, _ = telegram_chat.handle_user_question(chat_id, "First question")

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == f"telegram-{chat_id}@aeds.local").first()
            first_thread_id = session.query(QueryLog).filter(QueryLog.user_id == user.id).first().thread_id
        finally:
            session.close()

        message = telegram_chat.start_new_conversation(chat_id)
        assert "new conversation" in message.lower()

        telegram_chat.handle_user_question(chat_id, "Second question")

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == f"telegram-{chat_id}@aeds.local").first()
            logs = session.query(QueryLog).filter(QueryLog.user_id == user.id).order_by(QueryLog.id).all()
            assert logs[1].thread_id != first_thread_id
            assert logs[0].thread_id == first_thread_id
        finally:
            session.close()
    finally:
        _cleanup(chat_id)


def test_feedback_records_the_rating():
    chat_id = "pytest_fb_1"
    try:
        _, query_log_id = telegram_chat.handle_user_question(chat_id, "A question")
        assert query_log_id is not None

        result = telegram_chat.record_feedback(chat_id, query_log_id, 1)
        assert "Thanks" in result

        session = SessionLocal()
        try:
            entry = session.get(QueryLog, query_log_id)
            assert entry.rating == 1
        finally:
            session.close()
    finally:
        _cleanup(chat_id)


def test_feedback_rejects_an_invalid_rating():
    chat_id = "pytest_fb_2"
    try:
        _, query_log_id = telegram_chat.handle_user_question(chat_id, "A question")
        result = telegram_chat.record_feedback(chat_id, query_log_id, 5)
        assert "Invalid" in result
    finally:
        _cleanup(chat_id)


def test_feedback_refuses_to_rate_another_chats_question():
    chat_a, chat_b = "pytest_fb_owner", "pytest_fb_intruder"
    try:
        _, query_log_id = telegram_chat.handle_user_question(chat_a, "A question")

        result = telegram_chat.record_feedback(chat_b, query_log_id, 1)
        assert "Can't rate" in result

        session = SessionLocal()
        try:
            entry = session.get(QueryLog, query_log_id)
            assert entry.rating is None
        finally:
            session.close()
    finally:
        _cleanup(chat_a)
        _cleanup(chat_b)


def test_format_reply_labels_an_outdated_source():
    text = telegram_chat._format_reply(
        "Some answer.",
        [{"source_id": "old_doc", "page": None, "url": None, "expired_since": "2026-07-15"}],
    )
    assert "old_doc" in text
    assert "outdated since 2026-07-15" in text


def test_format_reply_includes_a_source_url():
    text = telegram_chat._format_reply(
        "Some answer.",
        [{"source_id": "doc", "page": None, "url": "https://example.com/doc", "expired_since": None}],
    )
    assert "https://example.com/doc" in text


def test_format_reply_dedupes_repeated_sources():
    text = telegram_chat._format_reply(
        "Some answer.",
        [
            {"source_id": "doc", "page": 1, "url": None, "expired_since": None},
            {"source_id": "doc", "page": 2, "url": None, "expired_since": None},
        ],
    )
    assert text.count("doc") == 1
