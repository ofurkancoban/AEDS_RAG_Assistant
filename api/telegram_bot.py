"""Telegram bot integration for the three admin review queues (source
changes, pending submissions, pending answers): push notifications with
inline Approve/Reject/Dismiss buttons, and a background long-poll loop that
turns a button press into the same action the admin panel's own
approve/reject/dismiss endpoints perform.

Why long polling, not a webhook. A webhook needs a public HTTPS URL Telegram
can reach, which most deployments - and every local dev setup - don't have
without extra infra (a tunnel, a reverse-proxy cert). getUpdates long polling
works identically in both, at the cost of one background thread holding a
~25s HTTP request open at a time, which is negligible next to this app's
actual load.

Why answer-review notifications are pull, not push. Source changes are rare
(a nightly cron finds a handful at most) and submissions are user-initiated
and infrequent, so pushing each one is reasonable. A CachedAnswer row is
created on every distinct question a student asks though - pushing one per
row would turn a normal day of usage into a constant stream of phone
notifications. Answer review is available via the same Approve/Reject
buttons, but only on request: send the bot /pending.

Trust model. The bot only acts on updates from the configured
TELEGRAM_CHAT_ID (see config.py); everything else is ignored. There is no
further login on the Telegram side, so that chat id is equivalent to an admin
session - keep .env private.
"""

import contextlib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}"
# Telegram's own long-poll timeout is capped well under a minute; this leaves
# margin for the request itself on top of the server-side wait.
_REQUEST_TIMEOUT = 35
_LONG_POLL_SECONDS = 25
# Telegram's hard cap is 4096 characters per message. Leaving real room under
# it matters here specifically: this text is what an admin approves or
# rejects from, so a truncated answer risks a decision made blind to content
# that was cut off, not a rounding choice on how much preview is enough.
_CONTENT_PREVIEW_CHARS = 3500


def _enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _api_url(method: str) -> str:
    return f"{_API_BASE.format(token=settings.telegram_bot_token)}/{method}"


def send_message(text: str, reply_markup: dict | None = None, chat_id: str | None = None) -> int | None:
    """Posts to `chat_id`, or the configured admin chat if omitted (every
    admin notify_*/pull-command call in this module relies on that default).
    Returns the sent message_id, or None if unconfigured or delivery failed
    - every caller treats a notification as best effort and never lets it
    block the action it's reporting on."""
    if not _enabled():
        return None
    payload: dict = {"chat_id": chat_id or settings.telegram_chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(_api_url("sendMessage"), json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()["result"]["message_id"]
    except Exception as exc:
        logger.warning("Telegram send_message failed: %s", exc)
        return None


def _edit_message(chat_id: str, message_id: int, text: str) -> None:
    try:
        response = requests.post(
            _api_url("editMessageText"),
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Telegram editMessageText failed: %s", exc)


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    try:
        response = requests.post(
            _api_url("answerCallbackQuery"),
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Telegram answerCallbackQuery failed: %s", exc)


def _button(label: str, data: str) -> dict:
    return {"text": label, "callback_data": data}


def _send_typing(chat_id: str) -> None:
    try:
        response = requests.post(
            _api_url("sendChatAction"),
            json={"chat_id": chat_id, "action": "typing"},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Telegram sendChatAction failed: %s", exc)


# Telegram's own "typing..." indicator lasts about 5 seconds per call and
# needs to be re-sent to keep showing - a RAG answer can take well over that
# (retrieval + rerank + generation), so a single sendChatAction before the
# question is answered would flash briefly and then look like nothing is
# happening for the rest of the wait.
_TYPING_REFRESH_SECONDS = 4


@contextlib.contextmanager
def _typing_indicator(chat_id: str):
    """Keeps Telegram's "typing..." shown in `chat_id` for as long as the
    wrapped block runs, by pinging sendChatAction from a background thread
    every _TYPING_REFRESH_SECONDS. Best effort like everything else here - a
    failed ping never interrupts the actual work."""
    if not _enabled():
        yield
        return

    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            _send_typing(chat_id)
            stop.wait(_TYPING_REFRESH_SECONDS)

    thread = threading.Thread(target=_loop, name="telegram-typing", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


# A persistent reply keyboard (distinct from the per-message inline
# Approve/Reject/Dismiss keyboards above - Telegram's API only allows one or
# the other per message, via the same reply_markup field). Once sent, this
# stays pinned below the text box for the whole chat, across every later
# message - including ones that carry their own inline keyboard - until
# something explicitly replaces or removes it, so sending it once per
# category response is enough to keep it "always visible" rather than
# needing to attach it to every single message.
_MENU_LABELS = {
    "pending": "📋 Pending",
    "gaps": "📊 Gaps",
    "sources": "🔄 Sources",
    "stats": "📈 Stats",
}
_MAIN_MENU_KEYBOARD = {
    "keyboard": [
        [{"text": _MENU_LABELS["pending"]}, {"text": _MENU_LABELS["gaps"]}],
        [{"text": _MENU_LABELS["sources"]}, {"text": _MENU_LABELS["stats"]}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}
_LABEL_TO_CATEGORY = {label: category for category, label in _MENU_LABELS.items()}

# The official "/" command menu Telegram shows next to the text box -
# registered once at startup via setMyCommands (see set_bot_commands), a
# different mechanism from the persistent reply keyboard above but pointing
# at the same four categories, so either one works. Registered under the
# admin chat's own scope only (see set_bot_commands) - setMyCommands with no
# scope sets the SAME list for every chat, which would show these review-
# queue commands, and hint at their existence, to every student too. Worse
# than a cosmetic leak: a student tapping a visible "/pending" would send
# that literal text, which - being a non-admin chat - gets routed to the
# student Q&A path and answered as if it were a real question.
_ADMIN_BOT_COMMANDS = [
    {"command": "menu", "description": "Show the button menu"},
    {"command": "pending", "description": "Pending submissions & answers"},
    {"command": "gaps", "description": "Content gaps (unanswered questions)"},
    {"command": "sources", "description": "Pending source changes"},
    {"command": "stats", "description": "Corpus stats"},
]
# The default scope every other chat (i.e. every student) sees.
_DEFAULT_BOT_COMMANDS = [{"command": "start", "description": "Ask a question"}]


def set_bot_commands() -> None:
    """Registers two separate command lists: _DEFAULT_BOT_COMMANDS for every
    chat, and _ADMIN_BOT_COMMANDS layered on top of that for just the admin
    chat, via setMyCommands' per-chat scope. Called once from
    start_background_polling - best effort, like every other call in this
    module, since a failed registration should never stop the bot from
    otherwise working."""
    if not _enabled():
        return
    try:
        response = requests.post(
            _api_url("setMyCommands"), json={"commands": _DEFAULT_BOT_COMMANDS}, timeout=_REQUEST_TIMEOUT
        )
        response.raise_for_status()
        response = requests.post(
            _api_url("setMyCommands"),
            json={
                "commands": _ADMIN_BOT_COMMANDS,
                "scope": {"type": "chat", "chat_id": settings.telegram_chat_id},
            },
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Telegram setMyCommands failed: %s", exc)


_MD_HEADER_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE_RE = re.compile(r"`([^`]+)`")


def _strip_markdown(text: str) -> str:
    """This app's own answers are GFM (##headers, **bold**, `code`), and a
    plain sendMessage shows that syntax as literal characters instead of
    rendering it - unreadable clutter in a review notification (found live:
    an answer with several ### sections and **bold** names came through as
    one run-on line of stray # and * symbols). Stripped rather than converted
    to Telegram's own Markdown, which is a different, incompatible dialect
    (no headers, single *not double* asterisks for bold) - not worth getting
    exactly right for what's a quick heads-up, when the fully formatted
    answer is already one tap away in the admin panel."""
    text = _MD_HEADER_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    return text


def _truncate(text: str, limit: int = _CONTENT_PREVIEW_CHARS) -> str:
    text = _strip_markdown(text)
    return text if len(text) <= limit else text[:limit] + "…"


# --- Outbound notifications, one per review-queue kind -----------------

def notify_expiring_documents(expiring: list[tuple[str, object]]) -> None:
    """Sent by scripts/source_refresh.check_expiring_documents for any
    corpus file whose valid_until (see sources.json) is already past or
    within EXPIRY_WARNING_DAYS - the kind of staleness a hash-diff check
    against the live page can't catch, since the page itself may not have
    changed at all (e.g. an annual deadlines table, or a year-specific
    announcement page). No button: the fix is someone going to re-scrape or
    re-curate the file by hand, not a single approve/reject action."""
    lines = [f"{len(expiring)} corpus file(s) past or nearing their valid_until date:"]
    lines.extend(f"- {filename} (valid until {valid_until.date().isoformat()})" for filename, valid_until in expiring)
    send_message("\n".join(lines))


def notify_source_change(doc_id: int, filename: str, url: str | None) -> None:
    text = (
        f"Source changed: {filename}\n"
        f"{url or ''}\n\n"
        "Review the word-level diff in the admin panel, then Dismiss here "
        "once it's been curated (or found not to matter)."
    )
    send_message(text, {"inline_keyboard": [[_button("Dismiss", f"src:{doc_id}")]]})


def notify_source_draft(doc_id: int, filename: str, draft: str) -> None:
    """Sent alongside notify_source_change, only for the AUTO_DRAFT_ELIGIBLE
    sources in scripts/source_refresh.py where an LLM draft was generated.
    Approving writes `draft` over the curated file and re-ingests it -
    reject just discards the draft and leaves the ordinary Dismiss-only flow
    from notify_source_change in place."""
    text = f"Auto-draft ready for {filename} (from the source change above):\n\n{_truncate(draft)}"
    send_message(
        text,
        {"inline_keyboard": [[_button("Approve draft", f"sdapp:{doc_id}"), _button("Reject draft", f"sdrej:{doc_id}")]]},
    )


def notify_new_submission(sub_id: int, submission_type: str, source_id: str, content: str) -> None:
    text = f"New {submission_type} submission for '{source_id}':\n\n{_truncate(content)}"
    send_message(
        text,
        {"inline_keyboard": [[_button("Approve", f"sa:{sub_id}"), _button("Reject", f"sr:{sub_id}")]]},
    )


def notify_pending_answer(answer_id: int, question: str, answer: str) -> None:
    text = f"Q: {_truncate(question, 200)}\n\nA: {_truncate(answer)}"
    send_message(
        text,
        {"inline_keyboard": [[_button("Approve", f"aa:{answer_id}"), _button("Reject", f"ar:{answer_id}")]]},
    )


def _send_main_menu() -> None:
    send_message(
        "AEDS RAG admin bot. Pick a category below, or use the / commands:",
        _MAIN_MENU_KEYBOARD,
    )


# --- Inbound: button presses and the /pending command ------------------

def _dispatch_action(data: str) -> str:
    """Applies one button press. Mirrors the corresponding admin route in
    api/routes_admin.py exactly, minus the admin-session Depends() - the
    Telegram chat id is the trust boundary here (see module docstring)."""
    from config import settings
    from db.chroma_client import mark_deprecated
    from db.models import AnswerStatus, CachedAnswer, IngestedDocument, PendingSubmission, SessionLocal, SubmissionStatus
    from ingestion.chunker import ingest_and_record_file, ingest_approved_submission

    try:
        action, raw_id = data.split(":", 1)
        record_id = int(raw_id)
    except ValueError:
        return "Unrecognized action."

    session = SessionLocal()
    try:
        if action == "src":
            doc = session.get(IngestedDocument, record_id)
            if doc is None or doc.source_diff is None:
                return "Already handled."
            doc.source_diff = None
            session.commit()
            return "Dismissed."

        if action == "sdapp":
            doc = session.get(IngestedDocument, record_id)
            if doc is None or doc.source_draft is None:
                return "Already handled."
            path = settings.documents_dir / doc.filename
            path.write_text(doc.source_draft, encoding="utf-8")
            ingest_and_record_file(path, session)
            doc.source_diff = None
            doc.source_draft = None
            session.commit()
            return "Draft approved, file updated and re-ingested."

        if action == "sdrej":
            doc = session.get(IngestedDocument, record_id)
            if doc is None or doc.source_draft is None:
                return "Already handled."
            doc.source_draft = None
            session.commit()
            return "Draft rejected. Source is still flagged for manual review."

        if action in ("sa", "sr"):
            submission = session.get(PendingSubmission, record_id)
            if submission is None or submission.status != SubmissionStatus.PENDING:
                return "Already reviewed."
            if action == "sa":
                if submission.submission_type.value == "correction" and submission.related_chunk_id:
                    mark_deprecated(submission.related_chunk_id)
                ingest_approved_submission(
                    content=submission.content,
                    source_id=submission.source_id,
                    submission_id=submission.id,
                )
                submission.status = SubmissionStatus.APPROVED
            else:
                submission.status = SubmissionStatus.REJECTED
            submission.admin_note = "Reviewed via Telegram"
            submission.reviewed_at = datetime.now(timezone.utc)
            session.commit()
            return "Approved." if action == "sa" else "Rejected."

        if action in ("aa", "ar"):
            answer = session.get(CachedAnswer, record_id)
            if answer is None or answer.status != AnswerStatus.PENDING:
                return "Already reviewed."
            answer.status = AnswerStatus.APPROVED if action == "aa" else AnswerStatus.REJECTED
            answer.admin_note = "Reviewed via Telegram"
            answer.reviewed_at = datetime.now(timezone.utc)
            session.commit()
            return "Approved." if action == "aa" else "Rejected."

        return "Unrecognized action."
    finally:
        session.close()


def _send_pending_summary() -> None:
    """Handles /pending: pulls the current review queues on request rather
    than pushing one message per answer (see module docstring)."""
    from db.models import AnswerStatus, CachedAnswer, PendingSubmission, SessionLocal, SubmissionStatus

    session = SessionLocal()
    try:
        submissions = (
            session.query(PendingSubmission)
            .filter(PendingSubmission.status == SubmissionStatus.PENDING)
            .order_by(PendingSubmission.created_at.desc())
            .limit(10)
            .all()
        )
        answers = (
            session.query(CachedAnswer)
            .filter(CachedAnswer.status == AnswerStatus.PENDING)
            .order_by(CachedAnswer.created_at.desc())
            .limit(10)
            .all()
        )
        submission_data = [(s.id, s.submission_type.value, s.source_id, s.content) for s in submissions]
        answer_data = [(a.id, a.question, a.answer) for a in answers]
    finally:
        session.close()

    if not submission_data and not answer_data:
        send_message("Nothing pending.", _MAIN_MENU_KEYBOARD)
        return

    send_message(
        f"{len(submission_data)} submission(s), {len(answer_data)} answer(s) pending (up to 10 shown each):",
        _MAIN_MENU_KEYBOARD,
    )
    for sub_id, submission_type, source_id, content in submission_data:
        notify_new_submission(sub_id, submission_type, source_id, content)
    for answer_id, question, answer in answer_data:
        notify_pending_answer(answer_id, question, answer)


_GAPS_WINDOW_DAYS = 30
_GAPS_LIST_SIZE = 10


def _send_content_gaps_summary() -> None:
    """Handles /gaps: content_gaps (see api/routes_admin.py's get_analytics)
    is the most direct signal of what content the corpus is still missing -
    questions students actually asked that it could not answer, ranked by
    how often. Pulled on request rather than pushed: unlike a new submission
    or a changed source, there's no single moment a gap "happens" - it's a
    slow-moving trend, not an event worth interrupting someone over."""
    from collections import Counter
    from datetime import datetime, timedelta, timezone

    from db.models import QueryLog, SessionLocal

    since = datetime.now(timezone.utc) - timedelta(days=_GAPS_WINDOW_DAYS)
    session = SessionLocal()
    try:
        rows = session.query(QueryLog).filter(QueryLog.created_at >= since).all()
    finally:
        session.close()

    if not rows:
        send_message(f"No queries logged in the last {_GAPS_WINDOW_DAYS} days.", _MAIN_MENU_KEYBOARD)
        return

    unanswered_counts = Counter(r.question.strip() for r in rows if not r.answered).most_common(_GAPS_LIST_SIZE)
    thumbs_down_counts = Counter(r.question.strip() for r in rows if r.rating == -1).most_common(_GAPS_LIST_SIZE)

    lines = [
        f"Content gaps, last {_GAPS_WINDOW_DAYS} days: {len(rows)} queries, "
        f"{sum(1 for r in rows if not r.answered)} unanswered."
    ]
    lines.append("\nMost-asked unanswered questions:" if unanswered_counts else "\nNo unanswered questions.")
    lines.extend(f"{count}x - {question}" for question, count in unanswered_counts)
    if thumbs_down_counts:
        lines.append("\nMost thumbs-downed questions:")
        lines.extend(f"{count}x - {question}" for question, count in thumbs_down_counts)

    send_message(_truncate("\n".join(lines), limit=_CONTENT_PREVIEW_CHARS), _MAIN_MENU_KEYBOARD)


def _send_source_changes_summary() -> None:
    """Handles /sources (and the 'Sources' menu button): the pull-on-demand
    counterpart to notify_source_change's nightly push - lists every
    currently-flagged source change with its own Dismiss button, same as
    the admin panel's Knowledge Base > Source Changes section."""
    from db.models import IngestedDocument, SessionLocal
    from ingestion.chunker import load_source_urls

    session = SessionLocal()
    try:
        rows = (
            session.query(IngestedDocument)
            .filter(IngestedDocument.source_diff.isnot(None))
            .order_by(IngestedDocument.last_changed_at.desc())
            .all()
        )
        changed = [(d.id, d.filename) for d in rows]
    finally:
        session.close()

    if not changed:
        send_message("No pending source changes.", _MAIN_MENU_KEYBOARD)
        return

    urls = load_source_urls()
    send_message(f"{len(changed)} source(s) with a pending change:", _MAIN_MENU_KEYBOARD)
    for doc_id, filename in changed:
        notify_source_change(doc_id, filename, urls.get(filename))


def _send_stats_summary() -> None:
    """Handles /stats (and the 'Stats' menu button): a quick corpus/queue
    snapshot without opening the admin panel - the same counts
    api/routes_admin.py's get_stats exposes there."""
    from db.chroma_client import get_corpus_stats
    from db.models import AnswerStatus, CachedAnswer, IngestedDocument, PendingSubmission, SessionLocal, SubmissionStatus

    corpus = get_corpus_stats()
    session = SessionLocal()
    try:
        pending_submissions = (
            session.query(PendingSubmission).filter(PendingSubmission.status == SubmissionStatus.PENDING).count()
        )
        pending_answers = session.query(CachedAnswer).filter(CachedAnswer.status == AnswerStatus.PENDING).count()
        pending_source_changes = (
            session.query(IngestedDocument).filter(IngestedDocument.source_diff.isnot(None)).count()
        )
    finally:
        session.close()

    text = (
        f"Corpus: {corpus['total_chunks']} chunks across {corpus['total_sources']} sources.\n\n"
        f"Pending submissions: {pending_submissions}\n"
        f"Pending answers: {pending_answers}\n"
        f"Pending source changes: {pending_source_changes}"
    )
    send_message(text, _MAIN_MENU_KEYBOARD)


def _handle_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback_query(update["callback_query"])
    elif "message" in update:
        _handle_message(update["message"])


_CATEGORY_HANDLERS = {
    "pending": _send_pending_summary,
    "gaps": _send_content_gaps_summary,
    "sources": _send_source_changes_summary,
    "stats": _send_stats_summary,
}


_USER_WELCOME_TEXT = (
    "Hi! Ask me anything about the Applied Economics and Data Science "
    "programme - courses, deadlines, exams, accommodation, and more - and "
    "I'll answer from the official programme documents."
)


def _handle_user_message(chat_id: str, text: str) -> None:
    """Any chat other than TELEGRAM_CHAT_ID lands here (see _handle_message)
    - a student asking a question, not an admin action. Kept to a single
    /start special case plus "everything else is a question" rather than
    mirroring the admin bot's command surface, since a student has no
    review-queue actions to reach."""
    if not text:
        return
    if text == "/start":
        send_message(_USER_WELCOME_TEXT, chat_id=chat_id)
        return

    from api.telegram_chat import handle_user_question

    with _typing_indicator(chat_id):
        reply = handle_user_question(chat_id, text)
    send_message(reply, chat_id=chat_id)


def _handle_message(message: dict) -> None:
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if chat_id != str(settings.telegram_chat_id):
        _handle_user_message(chat_id, text)
        return

    if text in ("/start", "/menu"):
        _send_main_menu()
        return

    # A command ("/pending") and its matching persistent-keyboard button
    # ("📋 Pending") both resolve to the same category and the same handler -
    # from the bot's side, tapping a button is indistinguishable from typing
    # the command, since Telegram sends both as plain text messages.
    category = text.lstrip("/") if text.startswith("/") else _LABEL_TO_CATEGORY.get(text)
    handler = _CATEGORY_HANDLERS.get(category)
    if handler is not None:
        handler()


def _handle_callback_query(callback_query: dict) -> None:
    message = callback_query.get("message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(settings.telegram_chat_id):
        _answer_callback(callback_query["id"], "Not authorized.")
        return

    result_text = _dispatch_action(callback_query.get("data", ""))
    _answer_callback(callback_query["id"], result_text)

    message_id = message.get("message_id")
    original_text = message.get("text", "")
    if message_id is not None:
        _edit_message(chat_id, message_id, f"{original_text}\n\n[{result_text}]")


# Sized off the same capacity planning as the rest of the app (README's
# "Deployment" section: ~50 students total, 5-10 asking at once during a
# busy spell), not off any per-request cost calculation - the real ceiling
# is Ollama's own generation throughput (measured ~6.5 answers/min
# regardless of how many callers are waiting), which every submitted task
# ends up queuing behind together, the same way concurrent web /chat
# requests already do via FastAPI's own thread pool. This pool just needs
# enough workers that Telegram traffic isn't artificially bottlenecked
# below what Ollama can already absorb - it is not what protects capacity.
_UPDATE_POOL_WORKERS = 10

_chat_locks: dict[str, threading.Lock] = {}
_chat_locks_guard = threading.Lock()


def _extract_chat_id(update: dict) -> str | None:
    if "message" in update:
        chat_id = update["message"].get("chat", {}).get("id")
    elif "callback_query" in update:
        chat_id = (update["callback_query"].get("message") or {}).get("chat", {}).get("id")
    else:
        return None
    return str(chat_id) if chat_id is not None else None


def _get_chat_lock(chat_id: str) -> threading.Lock:
    with _chat_locks_guard:
        lock = _chat_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _chat_locks[chat_id] = lock
        return lock


def _process_update(update: dict) -> None:
    """Runs one update on a pool worker (see start_background_polling).
    Different chats run genuinely in parallel - the whole point, so one
    student's slow generation never blocks another's question, or the
    admin's own actions. The same chat is still serialised through its own
    lock: two messages from one Telegram chat processed in true parallel
    could each load and step the same LangGraph conversation checkpoint at
    once, corrupting it - a risk the single-threaded loop this replaces
    never had, so it needs its own guard here rather than relying on
    anything upstream."""
    chat_id = _extract_chat_id(update)
    try:
        if chat_id is None:
            _handle_update(update)
        else:
            with _get_chat_lock(chat_id):
                _handle_update(update)
    except Exception:
        logger.exception("Telegram update handling failed for update_id=%s", update.get("update_id"))


def _poll_loop(executor: ThreadPoolExecutor) -> None:
    offset = 0
    while True:
        if not _enabled():
            threading.Event().wait(30)
            continue
        try:
            response = requests.get(
                _api_url("getUpdates"),
                params={
                    "timeout": _LONG_POLL_SECONDS,
                    "offset": offset,
                    "allowed_updates": json.dumps(["message", "callback_query"]),
                },
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            updates = response.json().get("result", [])
        except Exception as exc:
            logger.warning("Telegram getUpdates failed: %s", exc)
            threading.Event().wait(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            executor.submit(_process_update, update)


def start_background_polling() -> None:
    """Starts the long-poll loop in a daemon thread, backed by a worker pool
    that runs each update's handling (see _process_update) so multiple
    Telegram chats - students asking questions, or a student and the admin
    at once - are served concurrently instead of queued one at a time
    behind the loop itself. A no-op when the bot isn't configured, beyond
    the thread idling in _poll_loop's own check - called unconditionally
    from api/main.py's startup so enabling the bot later only needs a .env
    change and a restart, not a code change."""
    if not _enabled():
        logger.info("Telegram bot not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset), skipping.")
        return
    set_bot_commands()
    executor = ThreadPoolExecutor(max_workers=_UPDATE_POOL_WORKERS, thread_name_prefix="telegram-update")
    thread = threading.Thread(target=_poll_loop, args=(executor,), name="telegram-poll", daemon=True)
    thread.start()
    logger.info("Telegram bot polling started (%d update worker(s)).", _UPDATE_POOL_WORKERS)
