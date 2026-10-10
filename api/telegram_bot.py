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

Trust model. Admin actions only come from TELEGRAM_CHAT_ID and
TELEGRAM_EXTRA_ADMIN_CHAT_IDS (see config.py's and _admin_chat_ids());
everything else is treated as a student asking a question. There is no
further login on the Telegram side, so those chat ids are equivalent to an
admin session - keep .env private.
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


def _admin_chat_ids() -> list[str]:
    """telegram_chat_id (the original, always-required admin) plus any
    telegram_extra_admin_chat_ids - the full set of chats treated as admin
    for both outbound notifications and inbound command/button access."""
    primary = [settings.telegram_chat_id] if settings.telegram_chat_id else []
    extra = [c.strip() for c in settings.telegram_extra_admin_chat_ids.split(",") if c.strip()]
    return primary + [c for c in extra if c not in primary]


def _notify_admins(text: str, reply_markup: dict | None = None) -> None:
    for chat_id in _admin_chat_ids():
        send_message(text, reply_markup=reply_markup, chat_id=chat_id)


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
    {"command": "provider", "description": "Show/switch the live LLM provider"},
    {"command": "budget", "description": "Today's LLM quota usage"},
    {"command": "health", "description": "App health check"},
    {"command": "evalnow", "description": "Run the golden-set quality eval now"},
    {"command": "broadcast", "description": "Message every Telegram user"},
]
# The default scope every other chat (i.e. every student) sees.
_DEFAULT_BOT_COMMANDS = [
    {"command": "start", "description": "Ask a question"},
    {"command": "new", "description": "Start a fresh conversation"},
]


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
        for chat_id in _admin_chat_ids():
            response = requests.post(
                _api_url("setMyCommands"),
                json={
                    "commands": _ADMIN_BOT_COMMANDS,
                    "scope": {"type": "chat", "chat_id": chat_id},
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


_HEADING_RE = re.compile(r"^#{1,6}\s*(.+)$", re.MULTILINE)


def _flatten_headings(text: str) -> str:
    """Source-refresh drafts (notify_source_draft) replace a whole curated
    .md file, so unlike a chat answer they are mostly headings and short
    lines. _strip_markdown's plain deletion just merges a heading's text
    into the surrounding wall of prose with no break at all - fine for a
    quick heads-up, unreadable for something an admin is meant to actually
    review before approving. This gives each heading a visible marker
    instead, applied before _strip_markdown/_truncate so their '#' deletion
    has nothing left to match."""
    text = _HEADING_RE.sub(lambda m: f"\n▸ {m.group(1).strip()}", text)
    return re.sub(r"\n{3,}", "\n\n", text)


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
    _notify_admins("\n".join(lines))


def notify_source_change(doc_id: int, filename: str, url: str | None, chat_id: str | None = None) -> None:
    text = (
        f"Source changed: {filename}\n"
        f"{url or ''}\n\n"
        "Review the word-level diff in the admin panel, then Dismiss here "
        "once it's been curated (or found not to matter)."
    )
    markup = {"inline_keyboard": [[_button("Dismiss", f"src:{doc_id}")]]}
    if chat_id is not None:
        send_message(text, markup, chat_id=chat_id)
    else:
        _notify_admins(text, markup)


def notify_source_draft(doc_id: int, filename: str, draft: str) -> None:
    """Sent alongside notify_source_change, only for the AUTO_DRAFT_ELIGIBLE
    sources in scripts/source_refresh.py where an LLM draft was generated.
    Approving writes `draft` over the curated file and re-ingests it -
    reject just discards the draft and leaves the ordinary Dismiss-only flow
    from notify_source_change in place."""
    text = f"Auto-draft ready for {filename} (from the source change above):\n\n{_truncate(_flatten_headings(draft))}"
    _notify_admins(
        text,
        {"inline_keyboard": [[_button("Approve draft", f"sdapp:{doc_id}"), _button("Reject draft", f"sdrej:{doc_id}")]]},
    )


def notify_new_submission(sub_id: int, submission_type: str, source_id: str, content: str, chat_id: str | None = None) -> None:
    """Pushed to every admin on a new submission; also reused by
    _send_pending_summary to render one already-pending item back to just
    the admin who asked for /pending (chat_id given) rather than
    re-broadcasting it to everyone."""
    text = f"New {submission_type} submission for '{source_id}':\n\n{_truncate(content)}"
    markup = {
        "inline_keyboard": [
            [_button("Approve", f"sa:{sub_id}"), _button("Edit", f"se:{sub_id}"), _button("Reject", f"sr:{sub_id}")]
        ]
    }
    if chat_id is not None:
        send_message(text, markup, chat_id=chat_id)
    else:
        _notify_admins(text, markup)


def notify_pending_answer(answer_id: int, question: str, answer: str, chat_id: str | None = None) -> None:
    text = f"Q: {_truncate(question, 200)}\n\nA: {_truncate(answer)}"
    markup = {
        "inline_keyboard": [
            [_button("Approve", f"aa:{answer_id}"), _button("Edit", f"ae:{answer_id}"), _button("Reject", f"ar:{answer_id}")]
        ]
    }
    if chat_id is not None:
        send_message(text, markup, chat_id=chat_id)
    else:
        _notify_admins(text, markup)


def notify_downvoted_answer(question: str, answer: str, answer_id: int | None) -> None:
    """A student rated an answer unhelpful. When the answer is in the review
    queue the usual review buttons come with it; otherwise (a follow-up
    question, which is never cached) the alert is for information only."""
    text = f"Rated unhelpful by a student.\n\nQ: {_truncate(question, 200)}\n\nA: {_truncate(answer)}"
    markup = None
    if answer_id is not None:
        markup = {
            "inline_keyboard": [
                [_button("Approve", f"aa:{answer_id}"), _button("Edit", f"ae:{answer_id}"), _button("Reject", f"ar:{answer_id}")]
            ]
        }
    _notify_admins(text, markup)


def _send_main_menu(chat_id: str) -> None:
    send_message(
        "AEDS RAG admin bot. Pick a category below, or use the / commands:",
        _MAIN_MENU_KEYBOARD,
        chat_id=chat_id,
    )


# --- Inbound: button presses and the /pending command ------------------

def _dispatch_action(data: str, chat_id: str) -> str:
    """Applies one button press. Mirrors the corresponding admin route in
    api/routes_admin.py exactly, minus the admin-session Depends() - the
    Telegram chat id is the trust boundary here (see module docstring)."""
    from config import settings
    from db.chroma_client import mark_deprecated
    from db.models import AnswerStatus, CachedAnswer, IngestedDocument, PendingSubmission, SessionLocal, SubmissionStatus
    from ingestion.chunker import ingest_and_record_file, ingest_approved_submission

    try:
        action, raw_id = data.split(":", 1)
    except ValueError:
        return "Unrecognized action."

    # Actions whose id is not a record's integer primary key - handled
    # before the int() parse below, which would otherwise reject all of them.
    if action == "prov":
        return _switch_provider(raw_id)
    if action == "evalgo":
        threading.Thread(target=_run_eval_now, args=(chat_id,), daemon=True, name="telegram-evalnow").start()
        return "Started - I'll message you when it finishes (this can take several minutes)."
    if action == "evalno":
        return "Cancelled."
    if action == "bcgo":
        with _pending_broadcasts_guard:
            text = _pending_broadcasts.pop(chat_id, None)
        if text is None:
            return "Nothing pending."
        threading.Thread(target=_run_broadcast, args=(text,), daemon=True, name="telegram-broadcast").start()
        return "Sending..."
    if action == "bcno":
        with _pending_broadcasts_guard:
            _pending_broadcasts.pop(chat_id, None)
        return "Cancelled."

    try:
        record_id = int(raw_id)
    except ValueError:
        return "Unrecognized action."

    if action in ("se", "ae"):
        _start_edit(chat_id, "submission" if action == "se" else "answer", record_id)
        return "Reply with the corrected text."

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


def _send_pending_summary(chat_id: str) -> None:
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
        send_message("Nothing pending.", _MAIN_MENU_KEYBOARD, chat_id=chat_id)
        return

    send_message(
        f"{len(submission_data)} submission(s), {len(answer_data)} answer(s) pending (up to 10 shown each):",
        _MAIN_MENU_KEYBOARD,
        chat_id=chat_id,
    )
    for sub_id, submission_type, source_id, content in submission_data:
        notify_new_submission(sub_id, submission_type, source_id, content, chat_id=chat_id)
    for answer_id, question, answer in answer_data:
        notify_pending_answer(answer_id, question, answer, chat_id=chat_id)


_GAPS_WINDOW_DAYS = 30
_GAPS_LIST_SIZE = 10


def _send_content_gaps_summary(chat_id: str) -> None:
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
        send_message(f"No queries logged in the last {_GAPS_WINDOW_DAYS} days.", _MAIN_MENU_KEYBOARD, chat_id=chat_id)
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

    send_message(_truncate("\n".join(lines), limit=_CONTENT_PREVIEW_CHARS), _MAIN_MENU_KEYBOARD, chat_id=chat_id)


def _send_source_changes_summary(chat_id: str) -> None:
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
        send_message("No pending source changes.", _MAIN_MENU_KEYBOARD, chat_id=chat_id)
        return

    urls = load_source_urls()
    send_message(f"{len(changed)} source(s) with a pending change:", _MAIN_MENU_KEYBOARD, chat_id=chat_id)
    for doc_id, filename in changed:
        notify_source_change(doc_id, filename, urls.get(filename), chat_id=chat_id)


def _send_stats_summary(chat_id: str) -> None:
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
    send_message(text, _MAIN_MENU_KEYBOARD, chat_id=chat_id)


def _send_provider_status(chat_id: str) -> None:
    """Handles /provider: shows the live (admin-switchable) LLM provider and
    offers one-tap buttons to switch it, mirroring the admin panel's RAG
    Configuration screen for the one setting worth reaching from a phone
    during an incident (a provider going down)."""
    from runtime_config import ALLOWED_LLM_PROVIDERS, active_chat_model, get_runtime_config

    runtime = get_runtime_config()
    text = f"Live provider: {runtime.llm_provider}\nModel: {active_chat_model()}"
    others = [p for p in ALLOWED_LLM_PROVIDERS if p != runtime.llm_provider]
    send_message(
        text,
        {"inline_keyboard": [[_button(f"Switch to {p}", f"prov:{p}") for p in others]]},
        chat_id=chat_id,
    )


def _switch_provider(provider: str) -> str:
    """Mirrors api/routes_admin.py's put_config provider-switch validation -
    refusing a switch to a provider with no configured key, since that would
    otherwise take live chat down for every user immediately."""
    from runtime_config import ALLOWED_LLM_PROVIDERS, update_runtime_config

    if provider not in ALLOWED_LLM_PROVIDERS:
        return "Unknown provider."
    if provider == "gemini" and not settings.gemini_api_key:
        return "Cannot switch to gemini: GEMINI_API_KEY is not set."
    if provider == "openrouter" and not settings.openrouter_api_key:
        return "Cannot switch to openrouter: OPENROUTER_API_KEY is not set."
    update_runtime_config(llm_provider=provider)
    return f"Switched to {provider}."


def _send_budget_status(chat_id: str) -> None:
    """Handles /budget: today's LLM call count against the live provider's
    daily ceiling (see llm_budget.py, tracked independently per provider) -
    the number that determines whether the assistant is about to start
    refusing new questions. Also reports the effective provider (the one
    actually answering) whenever a daily-budget fallback has taken over,
    since that is otherwise invisible from this command alone."""
    import llm_budget
    from runtime_config import get_runtime_config

    provider = get_runtime_config().llm_provider
    used = llm_budget.usage_today(provider)
    budget = llm_budget.daily_budget(provider)
    if budget <= 0:
        text = f"Provider: {provider}\nUsed today: {used} (no daily ceiling)"
    else:
        text = f"Provider: {provider}\nUsed today: {used}/{budget} ({llm_budget.remaining(provider)} remaining)"

    effective = llm_budget.effective_provider()
    if effective != provider:
        effective_used = llm_budget.usage_today(effective)
        effective_budget = llm_budget.daily_budget(effective)
        text += (
            f"\n\nBudget fallback active - actually answering via {effective} "
            f"({effective_used}/{effective_budget} used today)."
        )
    send_message(text, chat_id=chat_id)


def _send_health_status(chat_id: str) -> None:
    """Handles /health: an on-demand version of the automatic Telegram error
    alerting in api/main.py - "is everything actually working" rather than
    waiting to find out from an error."""
    from changelog import current_version
    from db.models import SessionLocal, User
    from runtime_config import active_chat_model, get_runtime_config

    db_ok = True
    try:
        session = SessionLocal()
        try:
            session.query(User.id).first()
        finally:
            session.close()
    except Exception:
        db_ok = False

    runtime = get_runtime_config()
    text = (
        f"Version: {current_version()}\n"
        f"Database: {'OK' if db_ok else 'UNREACHABLE'}\n"
        f"Live provider: {runtime.llm_provider} ({active_chat_model()})"
    )
    send_message(text, chat_id=chat_id)


def _send_evalnow_confirmation(chat_id: str) -> None:
    """Handles /evalnow: an on-demand trigger for the golden-set quality
    eval scripts/eval_and_notify.py otherwise only runs weekly by cron.
    Gated behind a confirmation because a run spends real LLM quota against
    whichever provider is live - see that script's own docstring for why
    this can exhaust an entire day's OpenRouter budget in one go."""
    from runtime_config import get_runtime_config

    provider = get_runtime_config().llm_provider
    send_message(
        f"This runs the full golden-set eval (~46 questions, 2-3 LLM calls "
        f"each) against the LIVE provider ({provider}). On a metered "
        f"provider this can consume the entire day's quota. Continue?",
        {"inline_keyboard": [[_button("Yes, run it", "evalgo:1"), _button("Cancel", "evalno:1")]]},
        chat_id=chat_id,
    )


def _run_eval_now(chat_id: str) -> None:
    """Runs on its own background thread (see _dispatch_action's "evalgo"
    handling) rather than inline - a full run can take several minutes, far
    past what should hold up a callback-query response."""
    from runtime_config import get_runtime_config
    from tests.eval_golden import load_cases, run

    provider = get_runtime_config().llm_provider
    try:
        cases = load_cases()
        all_passed = run(cases, verbose=False)
        status = "PASSED" if all_passed else "FAILED - run `PYTHONPATH=. python -m tests.eval_golden --verbose` on the server for details"
        send_message(f"Golden-set eval against {provider}: {status}", chat_id=chat_id)
    except Exception:
        logger.exception("Manual /evalnow run failed")
        send_message("Eval run crashed - check the server logs.", chat_id=chat_id)


_pending_broadcasts: dict[str, str] = {}
_pending_broadcasts_guard = threading.Lock()


def _start_broadcast(chat_id: str, text: str) -> None:
    """Handles /broadcast <message>: previews it with a recipient count and
    waits for explicit confirmation before actually sending - a mis-tapped
    or mis-typed broadcast reaching every student is not something to risk
    on a single command with no undo."""
    from db.models import SessionLocal, User

    if not text.strip():
        send_message("Usage: /broadcast <message>", chat_id=chat_id)
        return

    session = SessionLocal()
    try:
        count = session.query(User).filter(User.email.like("telegram-%"), User.is_guest.is_(True)).count()
    finally:
        session.close()

    if count == 0:
        send_message("No Telegram users to broadcast to yet.", chat_id=chat_id)
        return

    with _pending_broadcasts_guard:
        _pending_broadcasts[chat_id] = text
    send_message(
        f"Send this to {count} Telegram user(s)?\n\n{text}",
        {"inline_keyboard": [[_button("Yes, send", "bcgo:1"), _button("Cancel", "bcno:1")]]},
        chat_id=chat_id,
    )


def _run_broadcast(text: str) -> None:
    from db.models import SessionLocal, User

    session = SessionLocal()
    try:
        chat_ids = [
            u.email.removeprefix("telegram-").removesuffix("@aeds.local")
            for u in session.query(User).filter(User.email.like("telegram-%"), User.is_guest.is_(True)).all()
        ]
    finally:
        session.close()

    sent = sum(1 for cid in chat_ids if send_message(text, chat_id=cid) is not None)
    _notify_admins(f"Broadcast sent to {sent}/{len(chat_ids)} user(s).")


_pending_edits: dict[str, tuple[str, int]] = {}
_pending_edits_guard = threading.Lock()


def _start_edit(chat_id: str, kind: str, record_id: int) -> None:
    """Handles the "Edit" button on a submission or pending-answer
    notification: prompts with a force-reply so the admin's next message (as
    a reply to this prompt) is read as the corrected text - see
    _handle_message's reply_to_message check and _apply_edit."""
    with _pending_edits_guard:
        _pending_edits[chat_id] = (kind, record_id)
    send_message(
        f"Send the corrected {kind} text as a reply to this message.",
        {"force_reply": True, "selective": True},
        chat_id=chat_id,
    )


def _apply_edit(chat_id: str, new_text: str) -> None:
    from db.models import CachedAnswer, PendingSubmission, SessionLocal

    with _pending_edits_guard:
        pending = _pending_edits.pop(chat_id, None)
    if pending is None:
        return
    kind, record_id = pending

    if not new_text.strip():
        send_message("Empty text - edit cancelled.", chat_id=chat_id)
        return

    session = SessionLocal()
    try:
        if kind == "submission":
            row = session.get(PendingSubmission, record_id)
            if row is None:
                send_message("That submission no longer exists.", chat_id=chat_id)
                return
            row.content = new_text.strip()
        else:
            row = session.get(CachedAnswer, record_id)
            if row is None:
                send_message("That answer no longer exists.", chat_id=chat_id)
                return
            # Same rule as api/routes_admin.py's approve_answer: preserve
            # what the model actually produced the first time this answer is
            # ever edited, so a correction can always be compared against it.
            if not row.original_answer:
                row.original_answer = row.answer
            row.answer = new_text.strip()
        session.commit()
    finally:
        session.close()

    send_message(
        f"{kind.capitalize()} #{record_id} updated. Use the Approve/Reject buttons above "
        f"(or send /pending to see it again).",
        chat_id=chat_id,
    )


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
    "provider": _send_provider_status,
    "budget": _send_budget_status,
    "health": _send_health_status,
    "evalnow": _send_evalnow_confirmation,
}


_USER_WELCOME_TEXT = (
    "Hi! Ask me anything about the Applied Economics and Data Science "
    "programme - courses, deadlines, exams, accommodation, and more - and "
    "I'll answer from the official programme documents.\n\n"
    "Send /new anytime to start a fresh conversation."
)
_EXAMPLE_QUESTIONS = [
    "What is the application deadline?",
    "What are the admission requirements?",
    "How many ECTS credits do I need?",
]
_EXAMPLE_QUESTIONS_KEYBOARD = {
    "keyboard": [[{"text": q}] for q in _EXAMPLE_QUESTIONS],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


def _handle_user_message(chat_id: str, text: str) -> None:
    """Any chat not in _admin_chat_ids() lands here (see _handle_message) -
    a student asking a question, not an admin action. Kept to /start and
    /new special cases plus "everything else is a question" rather than
    mirroring the admin bot's command surface, since a student has no
    review-queue actions to reach."""
    if not text:
        return
    if text == "/start":
        send_message(_USER_WELCOME_TEXT, _EXAMPLE_QUESTIONS_KEYBOARD, chat_id=chat_id)
        return
    if text == "/new":
        from api.telegram_chat import start_new_conversation

        send_message(start_new_conversation(chat_id), chat_id=chat_id)
        return

    from api.telegram_chat import handle_user_question

    with _typing_indicator(chat_id):
        reply, query_log_id = handle_user_question(chat_id, text)
    reply_markup = None
    if query_log_id is not None:
        reply_markup = {
            "inline_keyboard": [[_button("👍", f"fb:{query_log_id}:1"), _button("👎", f"fb:{query_log_id}:-1")]]
        }
    send_message(reply, reply_markup, chat_id=chat_id)


def _handle_feedback_callback(chat_id: str, data: str) -> str:
    from api.telegram_chat import record_feedback

    try:
        _, log_id_str, rating_str = data.split(":", 2)
        return record_feedback(chat_id, int(log_id_str), int(rating_str))
    except ValueError:
        return "Unrecognized."


def _handle_message(message: dict) -> None:
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if chat_id not in _admin_chat_ids():
        _handle_user_message(chat_id, text)
        return

    if message.get("reply_to_message") and chat_id in _pending_edits:
        _apply_edit(chat_id, text)
        return

    if text in ("/start", "/menu"):
        _send_main_menu(chat_id)
        return
    if text.startswith("/broadcast"):
        _start_broadcast(chat_id, text[len("/broadcast"):].strip())
        return

    # A command ("/pending") and its matching persistent-keyboard button
    # ("📋 Pending") both resolve to the same category and the same handler -
    # from the bot's side, tapping a button is indistinguishable from typing
    # the command, since Telegram sends both as plain text messages.
    category = text.lstrip("/") if text.startswith("/") else _LABEL_TO_CATEGORY.get(text)
    handler = _CATEGORY_HANDLERS.get(category)
    if handler is not None:
        handler(chat_id)


def _handle_callback_query(callback_query: dict) -> None:
    message = callback_query.get("message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))
    data = callback_query.get("data", "")

    if chat_id in _admin_chat_ids():
        result_text = _dispatch_action(data, chat_id)
    elif data.startswith("fb:"):
        result_text = _handle_feedback_callback(chat_id, data)
    else:
        result_text = "Not authorized."

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
