"""New admin-side Telegram bot features: multi-admin broadcast targeting,
live provider switching, budget/health reporting, and the edit-before-approve
flow. Network calls are never exercised here (see test_telegram_isolation.py
for that guarantee) - these test the pure dispatch/DB logic underneath."""

from config import settings
from db.models import CachedAnswer, PendingSubmission, Role, SessionLocal, SubmissionType, User


def test_admin_chat_ids_includes_primary_and_extras(monkeypatch):
    from api import telegram_bot

    monkeypatch.setattr(settings, "telegram_chat_id", "111")
    monkeypatch.setattr(settings, "telegram_extra_admin_chat_ids", "222, 333")
    assert telegram_bot._admin_chat_ids() == ["111", "222", "333"]


def test_admin_chat_ids_deduplicates(monkeypatch):
    from api import telegram_bot

    monkeypatch.setattr(settings, "telegram_chat_id", "111")
    monkeypatch.setattr(settings, "telegram_extra_admin_chat_ids", "111, 222")
    assert telegram_bot._admin_chat_ids() == ["111", "222"]


def test_admin_chat_ids_handles_empty_extra(monkeypatch):
    from api import telegram_bot

    monkeypatch.setattr(settings, "telegram_chat_id", "111")
    monkeypatch.setattr(settings, "telegram_extra_admin_chat_ids", "")
    assert telegram_bot._admin_chat_ids() == ["111"]


def test_switch_provider_rejects_unknown_name():
    from api.telegram_bot import _switch_provider

    assert "Unknown" in _switch_provider("not-a-real-provider")


def test_switch_provider_refuses_without_a_configured_key(monkeypatch):
    from api.telegram_bot import _switch_provider

    monkeypatch.setattr(settings, "gemini_api_key", "")
    result = _switch_provider("gemini")
    assert "GEMINI_API_KEY" in result


def test_switch_provider_succeeds_and_updates_runtime_config(monkeypatch):
    from api.telegram_bot import _switch_provider
    from runtime_config import get_runtime_config

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    result = _switch_provider("openrouter")
    assert "Switched to openrouter" in result
    assert get_runtime_config().llm_provider == "openrouter"


def test_daily_budget_wrapper_matches_the_live_provider(monkeypatch):
    import llm_budget
    from runtime_config import update_runtime_config

    monkeypatch.setattr(settings, "daily_llm_call_budget", -1)
    update_runtime_config(llm_provider="gemini")
    assert llm_budget.daily_budget() == 450


def _make_admin_submission(session) -> int:
    user = User(email="submitter@example.com", hashed_password="x", role=Role.USER)
    session.add(user)
    session.commit()
    submission = PendingSubmission(
        submitted_by_id=user.id,
        submission_type=SubmissionType.NEW_INFO,
        source_id="general",
        content="Original text",
    )
    session.add(submission)
    session.commit()
    return submission.id


def test_apply_edit_updates_submission_content():
    from api.telegram_bot import _apply_edit, _pending_edits

    session = SessionLocal()
    try:
        sub_id = _make_admin_submission(session)
    finally:
        session.close()

    _pending_edits["chat_x"] = ("submission", sub_id)
    _apply_edit("chat_x", "Corrected text")

    session = SessionLocal()
    try:
        row = session.get(PendingSubmission, sub_id)
        assert row.content == "Corrected text"
    finally:
        session.close()
    assert "chat_x" not in _pending_edits


def test_apply_edit_preserves_the_original_answer_once():
    from api.telegram_bot import _apply_edit, _pending_edits

    session = SessionLocal()
    try:
        answer = CachedAnswer(
            question="Q?",
            question_normalized="q?",
            embedding="[]",
            answer="First draft",
        )
        session.add(answer)
        session.commit()
        answer_id = answer.id
    finally:
        session.close()

    _pending_edits["chat_y"] = ("answer", answer_id)
    _apply_edit("chat_y", "Better answer")

    session = SessionLocal()
    try:
        row = session.get(CachedAnswer, answer_id)
        assert row.answer == "Better answer"
        assert row.original_answer == "First draft"
    finally:
        session.close()


def test_apply_edit_with_empty_text_is_cancelled_not_blanked():
    from api.telegram_bot import _apply_edit, _pending_edits

    session = SessionLocal()
    try:
        sub_id = _make_admin_submission(session)
    finally:
        session.close()

    _pending_edits["chat_z"] = ("submission", sub_id)
    _apply_edit("chat_z", "   ")

    session = SessionLocal()
    try:
        row = session.get(PendingSubmission, sub_id)
        assert row.content == "Original text"
    finally:
        session.close()


def test_dispatch_action_unrecognized_string_id_does_not_crash():
    """A callback whose id is not an integer (e.g. a stray "sa:abc") must be
    reported as unrecognized, not raise - before the "prov"/"evalgo"/etc.
    special-casing was added, this path threw ValueError uncaught."""
    from api.telegram_bot import _dispatch_action

    assert _dispatch_action("sa:not-a-number", "chat_id") == "Unrecognized action."
