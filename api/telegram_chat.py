"""Lets any Telegram user ask the RAG assistant a question, through the same
bot as the admin review tools but gated the other way: any chat that is NOT
TELEGRAM_CHAT_ID is a student asking a question, not an admin action - see
api/telegram_bot.py's _handle_message, which routes here.

Mirrors api/routes_chat.py's POST /chat handler closely and deliberately -
same rate limiter object, same daily budget check, same semantic cache
module, same run_chat call, same auto-flagged-contribution path - so a
question asked through Telegram behaves identically to one asked through
the web UI. It is not a wrapper around the HTTP endpoint itself (a loopback
call would work, but needs the API's own bound host/port known here, for no
real benefit within the same process); instead it calls the same
already-reusable building blocks that endpoint calls, without going through
FastAPI's request/session dependency injection, which this context doesn't
have.

Identity: each distinct Telegram chat gets one persistent guest User row
(email f"telegram-{chat_id}@aeds.local"), created on first message - this
is what gives a chat its own rate-limit bucket (via get_chat_limiter(), the
same key format as the web UI: "user:<id>") and its own conversation
thread, exactly like a browser tab's own guest token. The whole chat shares
one ongoing thread_id ("{user.id}:telegram") rather than starting a fresh
thread per message, since Telegram has no "new conversation" affordance of
its own.

No IP-layer backstop (api.rate_limit.get_chat_ip_limiter): Telegram gives no
usable per-caller network address here, so the per-chat identity limiter
carries the weight the IP layer normally shares with it. A chat_id is not
free to mint the way a guest browser token is, which is what makes this an
acceptable gap rather than an open door.
"""

import json
import logging
import secrets
import time

logger = logging.getLogger(__name__)

# Same ceiling as api/telegram_bot.py's own message previews - Telegram's
# hard cap is 4096 characters per message.
_ANSWER_PREVIEW_CHARS = 3500


def _get_or_create_telegram_user(session, chat_id: str):
    from api.auth import hash_password
    from db.models import Role, User

    email = f"telegram-{chat_id}@aeds.local"
    user = session.query(User).filter(User.email == email).first()
    if user is not None:
        return user
    user = User(
        email=email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        role=Role.USER,
        is_guest=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _format_reply(answer: str, sources: list) -> str:
    from api.telegram_bot import _truncate

    text = _truncate(answer, limit=_ANSWER_PREVIEW_CHARS)
    source_ids = sorted({s["source_id"] if isinstance(s, dict) else s.source_id for s in sources})
    if source_ids:
        text += "\n\nSources: " + ", ".join(source_ids)
    return text


def handle_user_question(chat_id: str, question: str) -> str:
    """Answers one question from a non-admin Telegram chat. Always returns a
    string to send back - a friendly message on rate limit, budget
    exhaustion, or error, never an exception - since this runs inside the
    bot's poll loop, which must never go down over one bad turn."""
    import llm_budget
    from api.rate_limit import check_and_record, get_chat_limiter
    from db import semantic_cache
    from db.chroma_client import get_embeddings
    from db.models import ChatMessage, PendingSubmission, QueryLog, SessionLocal, SubmissionType
    from graph.build_graph import is_cacheable_turn, run_chat

    session = SessionLocal()
    try:
        user = _get_or_create_telegram_user(session, chat_id)
        thread_id = f"{user.id}:telegram"
        client_key = f"user:{user.id}"

        # Checked before the cache lookup, matching /chat: a throttled chat
        # shouldn't spend the embedding call either.
        if not get_chat_limiter().check_and_record(client_key):
            return "Too many questions in a short period - please wait a little and try again."

        started = time.monotonic()

        cacheable = is_cacheable_turn(thread_id)
        embedding = None
        hit = None
        if cacheable:
            embedding = get_embeddings().embed_query(question)
            hit = semantic_cache.lookup(session, question, embedding)

        if hit is not None:
            semantic_cache.record_hit(session, hit)
            session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="user", content=question))
            session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="assistant", content=hit.answer))
            sources = json.loads(hit.sources_json)
            session.add(
                QueryLog(
                    question=question,
                    thread_id=thread_id,
                    user_id=user.id,
                    answered=True,
                    source_ids=",".join(sorted({s["source_id"] for s in sources})),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    served_from_cache=True,
                )
            )
            session.commit()
            return _format_reply(hit.answer, sources)

        if not llm_budget.has_headroom():
            return "The assistant has reached its daily question limit and will reset tomorrow."

        result = run_chat(thread_id=thread_id, question=question, source_id_filter=None)

        session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="user", content=question))
        session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="assistant", content=result["answer"]))

        detected = result.get("detected_contribution")
        submission = None
        if detected and check_and_record(client_key):
            submission = PendingSubmission(
                submitted_by_id=user.id,
                submission_type=SubmissionType(detected["type"]),
                source_id="general",
                content=detected["content"],
            )
            session.add(submission)

        session.commit()

        if submission is not None:
            from api.telegram_bot import notify_new_submission

            notify_new_submission(submission.id, submission.submission_type.value, submission.source_id, submission.content)

        # Only successful, grounded, time-independent answers are cached -
        # same reasoning as _maybe_store_cache in api/routes_chat.py.
        if cacheable and result.get("answered") and not result.get("time_sensitive"):
            semantic_cache.store(
                session,
                question=question,
                embedding=embedding,
                answer=result["answer"],
                sources=result["sources"],
                retrieval=result.get("retrieval", []),
            )

        session.add(
            QueryLog(
                question=question,
                thread_id=thread_id,
                user_id=user.id,
                answered=bool(result.get("answered", True)),
                source_ids=",".join(sorted({s["source_id"] if isinstance(s, dict) else s.source_id for s in result["sources"]})),
                latency_ms=int((time.monotonic() - started) * 1000),
                served_from_cache=False,
            )
        )
        session.commit()

        return _format_reply(result["answer"], result["sources"])
    except Exception:
        logger.exception("Telegram question handling failed for chat_id=%s", chat_id)
        return "Something went wrong answering that - please try again."
    finally:
        session.close()
