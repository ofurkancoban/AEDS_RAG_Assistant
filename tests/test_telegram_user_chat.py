"""api/telegram_chat.py: lets a non-admin Telegram chat ask the RAG assistant
a question. Stubs graph.build_graph.run_chat directly (not via
tests.conftest._stub_pipeline, which patches api.routes_chat's own copy of
the name - api/telegram_chat.py imports run_chat lazily from its source
module inside the function, so it needs its own stub target)."""

import pytest

from api import telegram_chat
from db.models import ChatMessage, QueryLog, SessionLocal, User

STUB_ANSWER = "Stubbed telegram answer."


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch):
    import graph.build_graph as build_graph

    def fake_run_chat(thread_id: str, question: str, source_id_filter=None):
        return {
            "answer": STUB_ANSWER,
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
            session.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
            session.query(QueryLog).filter(QueryLog.user_id == user.id).delete()
            session.delete(user)
            session.commit()
    finally:
        session.close()


def test_first_message_creates_a_guest_user_and_answers():
    chat_id = "pytest_chat_1"
    try:
        reply, query_log_id = telegram_chat.handle_user_question(chat_id, "A question")
        assert STUB_ANSWER in reply
        assert "stub_source" in reply

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == f"telegram-{chat_id}@aeds.local").first()
            assert user is not None
            assert user.is_guest is True

            messages = session.query(ChatMessage).filter(ChatMessage.user_id == user.id).all()
            assert [m.role for m in messages] == ["user", "assistant"]

            logs = session.query(QueryLog).filter(QueryLog.user_id == user.id).all()
            assert len(logs) == 1
            assert logs[0].thread_id == f"{user.id}:telegram"
            assert query_log_id == logs[0].id
        finally:
            session.close()
    finally:
        _cleanup(chat_id)


def test_same_chat_id_reuses_the_same_user_and_thread():
    chat_id = "pytest_chat_2"
    try:
        telegram_chat.handle_user_question(chat_id, "First question")
        telegram_chat.handle_user_question(chat_id, "Second question")

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == f"telegram-{chat_id}@aeds.local").first()
            logs = session.query(QueryLog).filter(QueryLog.user_id == user.id).all()
            assert len(logs) == 2
            assert logs[0].thread_id == logs[1].thread_id
        finally:
            session.close()
    finally:
        _cleanup(chat_id)


def test_different_chat_ids_get_isolated_users():
    chat_a, chat_b = "pytest_chat_a", "pytest_chat_b"
    try:
        telegram_chat.handle_user_question(chat_a, "Question from A")
        telegram_chat.handle_user_question(chat_b, "Question from B")

        session = SessionLocal()
        try:
            user_a = session.query(User).filter(User.email == f"telegram-{chat_a}@aeds.local").first()
            user_b = session.query(User).filter(User.email == f"telegram-{chat_b}@aeds.local").first()
            assert user_a.id != user_b.id
        finally:
            session.close()
    finally:
        _cleanup(chat_a)
        _cleanup(chat_b)


def test_rate_limit_blocks_before_calling_the_pipeline(monkeypatch):
    chat_id = "pytest_chat_throttled"
    try:
        from api.rate_limit import get_chat_limiter

        session = SessionLocal()
        try:
            user = telegram_chat._get_or_create_telegram_user(session, chat_id)
            key = f"user:{user.id}"
        finally:
            session.close()

        limiter = get_chat_limiter()
        for _ in range(30):
            limiter.check_and_record(key)

        def _must_not_be_called(*args, **kwargs):
            raise AssertionError("run_chat must not be called once the rate limit is exhausted")

        import graph.build_graph as build_graph

        monkeypatch.setattr(build_graph, "run_chat", _must_not_be_called)

        reply, query_log_id = telegram_chat.handle_user_question(chat_id, "One question too many")
        assert "Too many questions" in reply
        assert query_log_id is None
    finally:
        _cleanup(chat_id)


def test_telegram_answers_are_tagged_with_that_origin(monkeypatch):
    import graph.build_graph as build_graph

    # This file's own _stub_pipeline fixture forces is_cacheable_turn False
    # for every test (see its docstring) - overridden here just for this one,
    # since only a cacheable turn ever reaches semantic_cache.store() at all.
    monkeypatch.setattr(build_graph, "is_cacheable_turn", lambda thread_id: True)

    chat_id = "pytest_chat_origin"
    try:
        _, query_log_id = telegram_chat.handle_user_question(chat_id, "A distinctly worded question")

        session = SessionLocal()
        try:
            log = session.get(QueryLog, query_log_id)
            assert log.origin == "telegram"

            from db.models import CachedAnswer

            cached = (
                session.query(CachedAnswer)
                .filter(CachedAnswer.question == "A distinctly worded question")
                .first()
            )
            assert cached is not None
            assert cached.origin == "telegram"
            session.delete(cached)
            session.commit()
        finally:
            session.close()
    finally:
        _cleanup(chat_id)
