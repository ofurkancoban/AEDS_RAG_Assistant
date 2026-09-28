"""Isolation between visitors, and the limits that bound one visitor's usage."""

from tests.conftest import STUB_ANSWER


def _ask(client, headers, message="What are the language requirements?", **extra):
    return client.post("/chat", json={"message": message, **extra}, headers=headers)


def test_a_new_thread_is_namespaced_to_its_owner(client, guest_headers):
    response = _ask(client, guest_headers)
    assert response.status_code == 200
    thread_id = response.json()["thread_id"]

    me = client.get("/auth/me", headers=guest_headers).json()
    # The owner id is what _resolve_thread_id checks on every later message.
    assert thread_id.startswith(f"{me['id']}:")


def test_a_thread_cannot_be_continued_by_another_visitor(client, guest_headers, other_guest_headers):
    thread_id = _ask(client, guest_headers).json()["thread_id"]

    stolen = _ask(client, other_guest_headers, message="Continue please", thread_id=thread_id)
    # thread_id is client-supplied and is the only key the checkpointer uses,
    # so without this the stranger's history is loaded into the answer and
    # their own message is appended to it.
    assert stolen.status_code == 403


def test_a_malformed_thread_id_is_refused(client, guest_headers):
    response = _ask(client, guest_headers, thread_id="no-owner-prefix")
    assert response.status_code == 403


def test_a_visitor_can_continue_their_own_thread(client, guest_headers):
    thread_id = _ask(client, guest_headers).json()["thread_id"]
    again = _ask(client, guest_headers, message="And for non-EU applicants?", thread_id=thread_id)
    assert again.status_code == 200
    assert again.json()["thread_id"] == thread_id


def test_feedback_is_limited_to_your_own_answers(client, guest_headers, other_guest_headers):
    log_id = _ask(client, guest_headers).json()["query_log_id"]
    assert log_id is not None

    theirs = client.post(
        "/chat/feedback", json={"query_log_id": log_id, "rating": -1}, headers=other_guest_headers
    )
    # query_log ids are sequential, so without the ownership test anyone could
    # walk 1..N and thumbs-down every answer in the system. 404 rather than 403
    # so the endpoint does not confirm the id exists.
    assert theirs.status_code == 404

    mine = client.post(
        "/chat/feedback", json={"query_log_id": log_id, "rating": -1}, headers=guest_headers
    )
    assert mine.status_code == 204


def test_feedback_rejects_ratings_outside_thumbs_up_or_down(client, guest_headers):
    log_id = _ask(client, guest_headers).json()["query_log_id"]
    response = client.post(
        "/chat/feedback", json={"query_log_id": log_id, "rating": 5}, headers=guest_headers
    )
    assert response.status_code == 400


def test_chat_limit_is_per_identity_not_per_address(client, guest_headers, other_guest_headers, monkeypatch):
    from api import rate_limit, routes_chat

    test_limiter = rate_limit.RateLimiter("test-chat-per-identity", [(2, 3600)])
    monkeypatch.setattr(routes_chat, "get_chat_limiter", lambda: test_limiter)

    assert _ask(client, guest_headers).status_code == 200
    assert _ask(client, guest_headers).status_code == 200
    assert _ask(client, guest_headers).status_code == 429

    # Both visitors are on the same address here (the test client always is),
    # which is exactly the campus-wifi case: one student exhausting their
    # allowance must not spend anyone else's.
    assert _ask(client, other_guest_headers).status_code == 200


def test_a_per_address_backstop_bounds_identity_farming(client, monkeypatch):
    from api import rate_limit, routes_chat

    test_limiter = rate_limit.RateLimiter("test-chat-per-ip", [(3, 3600)])
    monkeypatch.setattr(routes_chat, "get_chat_ip_limiter", lambda: test_limiter)

    allowed = 0
    for _ in range(5):
        # A fresh identity every time, which is what a script would do.
        token = client.post("/auth/guest").json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        if _ask(client, headers).status_code == 200:
            allowed += 1

    assert allowed == 3


def test_the_throttled_response_says_when_to_retry(client, guest_headers, monkeypatch):
    from api import rate_limit, routes_chat

    test_limiter = rate_limit.RateLimiter("test-retry-after", [(1, 3600)])
    monkeypatch.setattr(routes_chat, "get_chat_limiter", lambda: test_limiter)

    _ask(client, guest_headers)
    blocked = _ask(client, guest_headers)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_chat_records_both_sides_of_the_turn(client, guest_headers):
    from db.models import ChatMessage, SessionLocal

    _ask(client, guest_headers, message="Who teaches Econometrics?")

    session = SessionLocal()
    try:
        rows = session.query(ChatMessage).order_by(ChatMessage.id).all()
        assert [r.role for r in rows] == ["user", "assistant"]
        assert rows[0].content == "Who teaches Econometrics?"
        assert rows[1].content == STUB_ANSWER
    finally:
        session.close()


def test_the_origin_header_is_recorded_on_both_the_log_and_the_cached_answer(client, guest_headers):
    from db.models import CachedAnswer, QueryLog, SessionLocal

    headers = {**guest_headers, "Origin": "https://ofurkancoban.github.io"}
    _ask(client, headers, message="What are the admission requirements?")

    session = SessionLocal()
    try:
        log = session.query(QueryLog).order_by(QueryLog.id.desc()).first()
        cached = session.query(CachedAnswer).order_by(CachedAnswer.id.desc()).first()
        assert log.origin == "https://ofurkancoban.github.io"
        assert cached.origin == "https://ofurkancoban.github.io"
    finally:
        session.close()


def test_no_origin_header_is_recorded_as_none(client, guest_headers):
    from db.models import QueryLog, SessionLocal

    # guest_headers alone carries no Origin - a direct, non-browser API call.
    _ask(client, guest_headers, message="What are the exam regulations?")

    session = SessionLocal()
    try:
        log = session.query(QueryLog).order_by(QueryLog.id.desc()).first()
        assert log.origin is None
    finally:
        session.close()


def test_submissions_are_rate_limited(client, guest_headers, monkeypatch):
    from api import rate_limit, routes_chat

    monkeypatch.setattr(routes_chat, "check_and_record", rate_limit.RateLimiter("test-submissions", [(1, 3600)]).check_and_record)

    payload = {"submission_type": "new_info", "source_id": "general", "content": "Something to add"}
    assert client.post("/chat/submissions", json=payload, headers=guest_headers).status_code == 201
    assert client.post("/chat/submissions", json=payload, headers=guest_headers).status_code == 429
