"""Test harness for the API suite.

Everything here exists to make the FastAPI app testable without the machinery
it normally depends on. Three things are swapped out:

  the database   a fresh SQLite file per test session, so a run can never see
                 or damage data/sqlite/app.db.
  the lifespan   api.main's startup scans the document folder and embeds
                 anything new, which would load a 335M-parameter embedding
                 model before the first assertion ran. The app under test is
                 assembled from the same routers without that hook.
  the pipeline   run_chat and the query embedding are stubbed by default.
                 These tests are about who is allowed to do what, not about
                 answer quality - that is tests/eval_golden.py's job, and it
                 needs a live model precisely because it checks the answers.

The environment variables must be set before anything imports config, because
db.models builds its engine from settings at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="aeds-tests-"))
os.environ["SQLITE_PATH"] = str(_TMP / "app.db")
os.environ["CHECKPOINTER_SQLITE_PATH"] = str(_TMP / "checkpoints.db")
os.environ["CHROMA_PERSIST_DIR"] = str(_TMP / "chroma")
os.environ["JWT_SECRET"] = "test-secret-not-the-default"
os.environ["ENVIRONMENT"] = "development"
# Overrides whatever is in .env - without this, a dev machine set to
# gemini/openrouter for manual testing silently changes which
# api/rate_limit.py rules and llm_budget defaults the suite exercises (found
# live: test_capacity.py failed only because .env had LLM_PROVIDER=openrouter
# at the time, which api/rate_limit.py's module-level RateLimiter
# construction picks up same as everything else here).
os.environ["LLM_PROVIDER"] = "ollama"
# Overrides whatever is in .env - without this, a dev machine with a real bot
# configured sends real Telegram messages on every test run (found live: the
# fixture submission in test_submissions_are_rate_limited posted "New
# new_info submission for 'general': Something to add" to a real chat every
# time the suite ran, since api/routes_chat.py notifies on every submission
# and nothing here stopped it from using the real bot token).
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

from config import settings  # noqa: E402
from db.models import Base, Role, SessionLocal, User, engine, init_db  # noqa: E402

STUB_ANSWER = "Stubbed answer."
STUB_EMBEDDING = [0.0] * 8


@pytest.fixture(scope="session", autouse=True)
def _database():
    assert str(settings.sqlite_path).startswith(str(_TMP)), (
        "tests are pointed at the real database - refusing to run"
    )
    init_db()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def app(monkeypatch):
    """The real routers, mounted without api.main's model-loading lifespan."""
    from fastapi import FastAPI

    from api.routes_admin import router as admin_router
    from api.routes_auth import router as auth_router
    from api.routes_chat import router as chat_router

    instance = FastAPI()
    instance.include_router(auth_router)
    instance.include_router(chat_router)
    instance.include_router(admin_router)
    return instance


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Empty every table between tests.

    This covers the rate limiters too, since their windows are rows in
    rate_limit_events rather than process memory - without it one test's
    requests count against the next one's budget and failures depend on test
    order.
    """
    session = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()

    yield


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch):
    """Answer generation replaced with a canned result.

    Patched on api.routes_chat rather than at the source module because that is
    where the names were bound at import time.
    """
    from api import routes_chat

    def fake_run_chat(thread_id: str, question: str, source_id_filter=None):
        return {
            "answer": STUB_ANSWER,
            "sources": [{"source_id": "stub", "page": None, "url": None}],
            "retrieval": [],
            "node_latencies": {},
            "answered": True,
            "time_sensitive": False,
            "detected_contribution": None,
        }

    monkeypatch.setattr(routes_chat, "run_chat", fake_run_chat)
    monkeypatch.setattr(routes_chat, "_question_embedding", lambda question: list(STUB_EMBEDDING))
    monkeypatch.setattr(routes_chat, "is_cacheable_turn", lambda thread_id: True)
    yield


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


def _make_user(email: str, password: str, role: Role, is_guest: bool = False) -> User:
    from api.auth import hash_password

    session = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_guest=is_guest,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


@pytest.fixture
def admin_user():
    return _make_user("admin@example.com", "admin-password", Role.ADMIN)


@pytest.fixture
def admin_token(admin_user):
    from api.auth import create_access_token

    return create_access_token(admin_user)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def guest_headers(client):
    """A fresh anonymous identity, obtained the way the real UI obtains one."""
    response = client.post("/auth/guest")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def other_guest_headers(client):
    response = client.post("/auth/guest")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
