"""What a thumbs-down does beyond being counted.

A downvote is the most direct report of a wrong answer the system gets, so
it reaches an admin right away (Telegram) and, when the answer sits in the
review queue, moves it to the top of that queue. It never changes an
answer's review status on its own: ratings come from anonymous visitors.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.models import CachedAnswer, ChatMessage, QueryLog
from db.semantic_cache import _normalize


def _answer_text(session: Session, entry: QueryLog) -> str:
    """The answer this logged question received, from the conversation
    history (query_log itself does not keep the answer)."""
    asked = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.thread_id == entry.thread_id,
            ChatMessage.role == "user",
            ChatMessage.content == entry.question,
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )
    if asked is None:
        return ""
    answer = (
        session.query(ChatMessage)
        .filter(ChatMessage.thread_id == entry.thread_id, ChatMessage.id > asked.id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.id)
        .first()
    )
    return answer.content if answer else ""


def _cached_answer_for(session: Session, entry: QueryLog) -> CachedAnswer | None:
    """The review-queue row this turn's answer belongs to, if any.

    Only the first question of a thread is ever cached (see CachedAnswer), so
    a later question is not matched even when its text happens to equal a
    cached one: "why?" mid-conversation is not the cached "why?".
    """
    first_in_thread = (
        session.query(QueryLog.id).filter(QueryLog.thread_id == entry.thread_id).order_by(QueryLog.id).first()
    )
    if first_in_thread is None or first_in_thread[0] != entry.id:
        return None
    return (
        session.query(CachedAnswer)
        .filter(CachedAnswer.question_normalized == _normalize(entry.question))
        .first()
    )


def record_rating(session: Session, entry: QueryLog, rating: int) -> None:
    """Store a rating; on a new thumbs-down, flag the answer for review and
    tell the admins. Re-sending the same downvote does nothing more."""
    is_new_downvote = rating == -1 and entry.rating != -1
    entry.rating = rating
    cached = None
    if is_new_downvote:
        cached = _cached_answer_for(session, entry)
        if cached is not None:
            cached.downvotes = (cached.downvotes or 0) + 1
            cached.last_downvoted_at = datetime.now(timezone.utc)
    session.commit()

    if is_new_downvote:
        from api.telegram_bot import notify_downvoted_answer

        notify_downvoted_answer(
            question=entry.question,
            answer=cached.answer if cached is not None else _answer_text(session, entry),
            answer_id=cached.id if cached is not None else None,
        )
