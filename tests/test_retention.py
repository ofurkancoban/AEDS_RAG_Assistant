"""Retention: what is kept, what is dropped, and what is never touched."""

from datetime import datetime, timedelta, timezone

from db.models import ChatMessage, PendingSubmission, QueryLog, Role, SessionLocal, SubmissionType, User
from scripts.maintenance import prune_history


def _at(days_ago: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None)


def _guest(days_ago: int, email: str) -> int:
    session = SessionLocal()
    try:
        user = User(email=email, hashed_password="x", role=Role.USER, is_guest=True)
        user.created_at = _at(days_ago)
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


def _message(user_id: int, days_ago: int) -> None:
    session = SessionLocal()
    try:
        row = ChatMessage(thread_id=f"{user_id}:t", user_id=user_id, role="user", content="hi")
        row.created_at = _at(days_ago)
        session.add(row)
        session.commit()
    finally:
        session.close()


def _query(user_id: int, days_ago: int) -> None:
    session = SessionLocal()
    try:
        row = QueryLog(question="q", thread_id=f"{user_id}:t", user_id=user_id, answered=True)
        row.created_at = _at(days_ago)
        session.add(row)
        session.commit()
    finally:
        session.close()


def _counts():
    session = SessionLocal()
    try:
        return (
            session.query(ChatMessage).count(),
            session.query(QueryLog).count(),
            session.query(User).count(),
        )
    finally:
        session.close()


def test_transcripts_past_the_window_are_deleted_and_recent_ones_kept():
    user = _guest(200, "old@aeds.local")
    _message(user, days_ago=120)
    _message(user, days_ago=5)

    prune_history(chat_days=90, log_days=400, dry_run=False)

    chat, _, _ = _counts()
    assert chat == 1


def test_the_query_log_outlives_transcripts():
    user = _guest(200, "old@aeds.local")
    _message(user, days_ago=120)
    _query(user, days_ago=120)

    prune_history(chat_days=90, log_days=400, dry_run=False)

    chat, log, _ = _counts()
    # The analytics content-gap list is the most direct evidence of which
    # documents are missing, so it is kept far longer than the transcript.
    assert (chat, log) == (0, 1)


def test_a_dry_run_changes_nothing():
    user = _guest(200, "old@aeds.local")
    _message(user, days_ago=120)
    _query(user, days_ago=500)

    prune_history(chat_days=90, log_days=400, dry_run=True)

    assert _counts() == (1, 1, 1)


def test_a_guest_is_removed_once_nothing_references_it():
    user = _guest(200, "spent@aeds.local")
    _message(user, days_ago=120)

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        # Deleting the transcript in the same run is what makes this identity
        # collectable; a separate pass would have left it for a day.
        assert session.get(User, user) is None
    finally:
        session.close()


def test_a_guest_with_recent_activity_is_kept():
    user = _guest(200, "active@aeds.local")
    _message(user, days_ago=1)

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        assert session.get(User, user) is not None
    finally:
        session.close()


def test_a_guest_who_submitted_knowledge_is_kept():
    user = _guest(200, "contributor@aeds.local")
    session = SessionLocal()
    try:
        session.add(
            PendingSubmission(
                submitted_by_id=user,
                submission_type=SubmissionType.NEW_INFO,
                source_id="general",
                content="A fact.",
            )
        )
        session.commit()
    finally:
        session.close()

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        # submitted_by_id is NOT NULL, so removing the author would orphan a
        # row the admin still has to review.
        assert session.get(User, user) is not None
    finally:
        session.close()


def test_a_recently_created_guest_is_kept_even_with_no_activity():
    user = _guest(1, "justarrived@aeds.local")

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        # Someone who opened the app a minute ago has no rows yet; collecting
        # them would invalidate the token in their browser.
        assert session.get(User, user) is not None
    finally:
        session.close()


def test_the_shared_fallback_identity_is_never_collected():
    session = SessionLocal()
    try:
        shared = User(
            email="guest@aeds.local", hashed_password="x", role=Role.USER, is_guest=True
        )
        shared.created_at = _at(500)
        session.add(shared)
        session.commit()
        shared_id = shared.id
    finally:
        session.close()

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        # Every tokenless caller lands on this one row; churning its id on
        # each maintenance run would serve no purpose.
        assert session.get(User, shared_id) is not None
    finally:
        session.close()


def test_staff_accounts_are_never_collected():
    session = SessionLocal()
    try:
        admin = User(
            email="admin@example.com", hashed_password="x", role=Role.ADMIN, is_guest=False
        )
        admin.created_at = _at(900)
        session.add(admin)
        session.commit()
        admin_id = admin.id
    finally:
        session.close()

    prune_history(chat_days=90, log_days=400, dry_run=False)

    session = SessionLocal()
    try:
        assert session.get(User, admin_id) is not None
    finally:
        session.close()
