"""Guards against the Telegram bot ever making a real network call during the
test suite.

Found live: a fixture submission in test_api_chat.py posted a real Telegram
message on every test run, because api/routes_chat.py notifies on every
submission and nothing stopped it from using whatever real bot token was in
.env on the machine running the tests. tests/conftest.py now forces
TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID to empty strings before config is
imported - this file is what keeps that fix from silently regressing if
someone later touches conftest.py or adds a new notify_* call path.
"""

import threading
from datetime import datetime

import requests

from api import telegram_bot
from config import settings


def test_telegram_disabled_in_test_environment():
    """conftest.py must force these empty regardless of the real .env on the
    machine running the suite - this is the actual mechanism every other
    guarantee in this file rests on."""
    assert settings.telegram_bot_token == ""
    assert settings.telegram_chat_id == ""


def test_send_message_makes_no_network_call(monkeypatch):
    """Even if telegram_bot_token/chat_id were somehow set, send_message must
    refuse before ever touching the network - proven here by making any
    outbound HTTP call raise, not by trusting the config check alone."""

    def _fail(*args, **kwargs):
        raise AssertionError("send_message must not make a real HTTP request in tests")

    monkeypatch.setattr(requests, "post", _fail)
    monkeypatch.setattr(requests, "get", _fail)

    assert telegram_bot.send_message("test") is None


def test_notify_functions_make_no_network_call(monkeypatch):
    """Every outbound notification path (source change, new submission,
    pending answer, source draft) must be a no-op with no token configured -
    exercised directly rather than via the API routes that call them, so
    this stays a fast, isolated regression guard."""

    def _fail(*args, **kwargs):
        raise AssertionError("Telegram notification must not make a real HTTP request in tests")

    monkeypatch.setattr(requests, "post", _fail)
    monkeypatch.setattr(requests, "get", _fail)

    telegram_bot.notify_source_change(1, "some_file.md", "https://example.com")
    telegram_bot.notify_source_draft(1, "some_file.md", "draft text")
    telegram_bot.notify_new_submission(1, "new_info", "general", "Something to add")
    telegram_bot.notify_pending_answer(1, "A question?", "An answer.")
    telegram_bot.notify_expiring_documents([("some_file.md", datetime.now())])
    telegram_bot.set_bot_commands()
    telegram_bot._send_main_menu("some_chat_id")


def test_pull_commands_make_no_network_call(monkeypatch):
    """/pending, /gaps, /sources, /stats all query the DB directly and then
    call send_message - covered separately from the notify_* functions above
    since these build their own DB session rather than taking pre-fetched
    data as arguments."""

    def _fail(*args, **kwargs):
        raise AssertionError("Telegram pull command must not make a real HTTP request in tests")

    monkeypatch.setattr(requests, "post", _fail)
    monkeypatch.setattr(requests, "get", _fail)

    telegram_bot._send_pending_summary("some_chat_id")
    telegram_bot._send_content_gaps_summary("some_chat_id")
    telegram_bot._send_source_changes_summary("some_chat_id")
    telegram_bot._send_stats_summary("some_chat_id")


def test_menu_button_labels_resolve_to_known_categories():
    """Every label on the persistent reply keyboard must route to a real
    handler - a mismatch here means tapping a menu button silently does
    nothing, which is easy to miss since Telegram gives no error for an
    unrecognised plain-text message."""
    for category, label in telegram_bot._MENU_LABELS.items():
        assert telegram_bot._LABEL_TO_CATEGORY[label] == category
        assert category in telegram_bot._CATEGORY_HANDLERS


def test_admin_commands_are_not_in_the_default_command_list():
    """setMyCommands' default scope is visible to every chat, admin and
    student alike - the review-queue commands must only ever be registered
    under the admin chat's own scope (see set_bot_commands), never the
    default one, or a student's "/" menu leaks them and tapping one gets
    answered as if it were a real question (see set_bot_commands' docstring
    for how that happens)."""
    default_names = {c["command"] for c in telegram_bot._DEFAULT_BOT_COMMANDS}
    admin_names = {c["command"] for c in telegram_bot._ADMIN_BOT_COMMANDS}
    assert default_names.isdisjoint(admin_names)


def test_different_chats_process_in_parallel_same_chat_serialised(monkeypatch):
    """_process_update must let two different chats run genuinely at the
    same time (the whole point of the worker pool), while never letting two
    updates from the SAME chat run concurrently (see _process_update's
    docstring for why: a race there could step the same LangGraph
    checkpoint from two threads at once)."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    intervals: list[tuple[str, float, float]] = []
    lock = threading.Lock()

    def fake_handle_update(update):
        chat_id = telegram_bot._extract_chat_id(update)
        start = time.monotonic()
        time.sleep(0.2)
        end = time.monotonic()
        with lock:
            intervals.append((chat_id, start, end))

    monkeypatch.setattr(telegram_bot, "_handle_update", fake_handle_update)

    def make_update(uid, chat_id):
        return {"update_id": uid, "message": {"chat": {"id": chat_id}, "text": "hi"}}

    def overlaps(a, b):
        """a, b are (start, end) pairs."""
        return a[0] < b[1] and b[0] < a[1]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(telegram_bot._process_update, make_update(1, "chat_A")),
            pool.submit(telegram_bot._process_update, make_update(2, "chat_B")),
            pool.submit(telegram_bot._process_update, make_update(3, "chat_A")),
        ]
        for f in futures:
            f.result(timeout=5)

    by_chat = {}
    for chat_id, start, end in intervals:
        by_chat.setdefault(chat_id, []).append((start, end))

    # Different chats: at least one pair overlaps in time.
    a_interval = by_chat["chat_A"][0]
    b_interval = by_chat["chat_B"][0]
    assert overlaps(a_interval, b_interval), "different chats should run in parallel"

    # Same chat: its two updates must never overlap.
    a1, a2 = by_chat["chat_A"]
    assert not overlaps(a1, a2), "updates from the same chat must be serialised"


def test_typing_indicator_makes_no_network_call(monkeypatch):
    """Disabled (no token configured, as in every test) must not even start
    the background ping thread, let alone call the network from it."""

    def _fail(*args, **kwargs):
        raise AssertionError("Typing indicator must not make a real HTTP request in tests")

    monkeypatch.setattr(requests, "post", _fail)
    monkeypatch.setattr(requests, "get", _fail)

    with telegram_bot._typing_indicator("some_chat_id"):
        pass
