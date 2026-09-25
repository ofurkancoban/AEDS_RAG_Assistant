import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import llm_budget
from api.auth import get_current_user_or_guest
from api.rate_limit import chat_ip_limiter, chat_limiter, check_and_record, client_ip
from api.telegram_bot import notify_new_submission
from db import semantic_cache
from db.models import ChatMessage, PendingSubmission, QueryLog, SubmissionType, User, get_session
from graph.build_graph import is_cacheable_turn, run_chat, stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])


def _question_embedding(question: str) -> list[float]:
    from db.chroma_client import get_embeddings

    return get_embeddings().embed_query(question)


def _enforce_chat_limit(request: Request, user: User) -> None:
    """Two layers, checked together.

    The per-identity limit is the fair share one person gets. The per-IP one
    sits underneath it as a backstop: identities are cheap enough to mint that
    a script could cycle them, and this bounds the total coming from a single
    address to roughly what the hardware can serve anyway.

    The IP layer is deliberately loose enough that a shared campus address
    running many real students never reaches it.
    """
    ip_key = f"ip:{client_ip(request)}"
    if not chat_ip_limiter.check_and_record(ip_key):
        raise HTTPException(
            status_code=429,
            detail=(
                "This network has reached its shared question limit for now - "
                "please wait a little and try again."
            ),
            headers={"Retry-After": str(chat_ip_limiter.retry_after(ip_key))},
        )

    key = _client_key(request, user)
    if not chat_limiter.check_and_record(key):
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short period - please wait a little and try again.",
            headers={"Retry-After": str(chat_limiter.retry_after(key))},
        )


def _enforce_daily_budget() -> None:
    """Global ceiling across all clients (see llm_budget.py).

    Deliberately checked AFTER the cache lookup: a cache hit issues no LLM
    request, so it stays available once the budget is spent. The service
    degrades to answering only what it has answered before rather than going
    dark entirely.
    """
    if not llm_budget.has_headroom():
        raise HTTPException(
            status_code=503,
            detail=(
                "The assistant has reached its daily question limit and will reset tomorrow. "
                "Previously answered questions are still available in the meantime."
            ),
            headers={"Retry-After": str(_seconds_until_utc_midnight())},
        )


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((reset - now).total_seconds()))


def _record_turn(
    session: Session,
    *,
    thread_id: str,
    user: User,
    question: str,
    answer: str,
) -> None:
    session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="user", content=question))
    session.add(ChatMessage(thread_id=thread_id, user_id=user.id, role="assistant", content=answer))


def _lookup_cache(session: Session, payload: "ChatRequest", thread_id: str):
    """Shared by both chat endpoints. Returns (cacheable, embedding, hit).

    Factored out deliberately: the cache was originally added to /chat only,
    and once the UI moved to /chat/stream every real user question started
    bypassing it entirely. Keeping one implementation is what stops the two
    endpoints drifting apart again.

    Cache is consulted only for the opening question of a thread and only for
    unfiltered searches - a source_id_filter changes which chunks are
    eligible, so its answer isn't interchangeable with the unfiltered one.
    """
    cacheable = payload.source_id_filter is None and is_cacheable_turn(thread_id)
    if not cacheable:
        return False, None, None

    embedding = _question_embedding(payload.message)
    return True, embedding, semantic_cache.lookup(session, payload.message, embedding)


def _maybe_store_cache(session: Session, payload: "ChatRequest", cacheable: bool, embedding, result: dict) -> None:
    """Only successful, grounded, time-independent answers are worth replaying.
    Caching an "I couldn't find that" would keep serving the gap after the
    missing document is added, and caching a deadline countdown would restate
    a day count that silently drifts as it sits in cache."""
    if not (cacheable and result.get("answered") and not result.get("time_sensitive")):
        return
    semantic_cache.store(
        session,
        question=payload.message,
        embedding=embedding,
        answer=result["answer"],
        sources=result["sources"],
        retrieval=result.get("retrieval", []),
    )


def _log_query(
    session: Session,
    *,
    question: str,
    thread_id: str,
    user: User,
    answered: bool,
    sources: list,
    latency_ms: int,
    served_from_cache: bool,
) -> int:
    """Record the turn and return the log id, which the client sends back with
    a thumbs rating so the two can be tied together."""
    source_ids = ",".join(
        sorted({s["source_id"] if isinstance(s, dict) else s.source_id for s in sources})
    )
    entry = QueryLog(
        question=question,
        thread_id=thread_id,
        user_id=user.id,
        answered=answered,
        source_ids=source_ids,
        latency_ms=latency_ms,
        served_from_cache=served_from_cache,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry.id


def _new_thread_id(user: User) -> str:
    return f"{user.id}:{uuid.uuid4()}"


def _resolve_thread_id(payload: "ChatRequest", user: User) -> str:
    """Return the thread to continue, refusing one that belongs to someone else.

    thread_id is client-supplied and is the only key the LangGraph checkpointer
    uses, so without this check any caller could pass another user's thread id
    and have that conversation's history loaded into their own answer - and
    have their messages appended to that stranger's history in return. The
    "{user_id}:{uuid}" format already recorded the owner; nothing was reading
    it back.
    """
    if not payload.thread_id:
        return _new_thread_id(user)

    owner, _, remainder = payload.thread_id.partition(":")
    if not remainder or owner != str(user.id):
        raise HTTPException(status_code=403, detail="This conversation belongs to a different session")
    return payload.thread_id


def _client_key(request: Request, user: User) -> str:
    """Per-person key: one bucket per identity, guest or registered.

    Guests used to be keyed by IP, on the reasoning that a guest identity is
    free to obtain and so cannot be trusted as a limit key. That protected
    against identity farming but broke the actual deployment: on a shared
    campus address every student lands in the same bucket, which at the old
    numbers left them about two questions each.

    Obtaining an identity is itself rate limited (see guest_limiter), and
    _enforce_chat_limit keeps a per-IP backstop underneath this, so farming is
    still bounded - now without charging thirty people for one person's usage.
    """
    return f"user:{user.id}"


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    source_id_filter: str | None = None


class SourceOut(BaseModel):
    source_id: str
    page: int | None = None
    url: str | None = None


class RetrievedChunkOut(BaseModel):
    source_id: str
    snippet: str
    hybrid_score: float | None = None
    rerank_score: float | None = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    sources: list[SourceOut] = []
    auto_flagged_contribution: str | None = None
    retrieval: list[RetrievedChunkOut] = []
    node_latencies: dict[str, float] = {}
    query_log_id: int | None = None
    cached: bool = False


@router.post("", response_model=ChatResponse)
def chat(
    request: Request,
    payload: ChatRequest,
    user: User = Depends(get_current_user_or_guest),
    session: Session = Depends(get_session),
):
    thread_id = _resolve_thread_id(payload, user)
    started = time.monotonic()

    # Checked before the cache lookup so a throttled client cannot spend the
    # embedding either, and so the limit reflects requests made rather than
    # LLM calls avoided.
    _enforce_chat_limit(request, user)

    cacheable, embedding, hit = _lookup_cache(session, payload, thread_id)
    if hit is not None:
        semantic_cache.record_hit(session, hit)
        _record_turn(session, thread_id=thread_id, user=user, question=payload.message, answer=hit.answer)
        session.commit()
        sources = json.loads(hit.sources_json)
        log_id = _log_query(
            session,
            question=payload.message,
            thread_id=thread_id,
            user=user,
            answered=True,
            sources=sources,
            latency_ms=int((time.monotonic() - started) * 1000),
            served_from_cache=True,
        )
        return ChatResponse(
            thread_id=thread_id,
            answer=hit.answer,
            sources=sources,
            retrieval=json.loads(hit.retrieval_json),
            query_log_id=log_id,
            cached=True,
        )

    _enforce_daily_budget()

    result = run_chat(
        thread_id=thread_id,
        question=payload.message,
        source_id_filter=payload.source_id_filter,
    )

    _record_turn(session, thread_id=thread_id, user=user, question=payload.message, answer=result["answer"])

    auto_flagged_contribution = None
    detected = result.get("detected_contribution")
    # If a guest has hit the rate limit, the contribution is silently dropped
    # rather than failing the chat response itself - the answer the user is
    # actively waiting for shouldn't break because of unrelated abuse-prevention.
    if detected and check_and_record(_client_key(request, user)):
        submission = PendingSubmission(
            submitted_by_id=user.id,
            submission_type=SubmissionType(detected["type"]),
            source_id=payload.source_id_filter or "general",
            content=detected["content"],
        )
        session.add(submission)
        auto_flagged_contribution = detected["type"]

    session.commit()
    if auto_flagged_contribution:
        notify_new_submission(submission.id, submission.submission_type.value, submission.source_id, submission.content)

    _maybe_store_cache(session, payload, cacheable, embedding, result)

    log_id = _log_query(
        session,
        question=payload.message,
        thread_id=thread_id,
        user=user,
        answered=bool(result.get("answered", True)),
        sources=result["sources"],
        latency_ms=int((time.monotonic() - started) * 1000),
        served_from_cache=False,
    )

    return ChatResponse(
        thread_id=thread_id,
        answer=result["answer"],
        sources=result["sources"],
        auto_flagged_contribution=auto_flagged_contribution,
        retrieval=result.get("retrieval", []),
        node_latencies=result.get("node_latencies", {}),
        query_log_id=log_id,
    )


@router.post("/stream")
def chat_stream(
    request: Request,
    payload: ChatRequest,
    user: User = Depends(get_current_user_or_guest),
    session: Session = Depends(get_session),
):
    """Server-Sent Events version of /chat: emits 'token' events as the answer
    is generated so the UI can render it progressively, then one final 'done'
    event with sources/thread_id/auto_flagged_contribution - same information
    the non-streaming endpoint returns all at once, just split by arrival time
    rather than by content."""
    thread_id = _resolve_thread_id(payload, user)
    started = time.monotonic()

    # Both guards run before the StreamingResponse is returned so a rejection
    # is a normal 429 the client can read, rather than an error buried inside
    # an already-open event stream.
    _enforce_chat_limit(request, user)

    cacheable, embedding, hit = _lookup_cache(session, payload, thread_id)
    if hit is not None:
        semantic_cache.record_hit(session, hit)
        _record_turn(session, thread_id=thread_id, user=user, question=payload.message, answer=hit.answer)
        session.commit()
        sources = json.loads(hit.sources_json)
        log_id = _log_query(
            session,
            question=payload.message,
            thread_id=thread_id,
            user=user,
            answered=True,
            sources=sources,
            latency_ms=int((time.monotonic() - started) * 1000),
            served_from_cache=True,
        )
        cached_payload = {
            "thread_id": thread_id,
            "sources": sources,
            "auto_flagged_contribution": None,
            "final_answer": hit.answer,
            "retrieval": json.loads(hit.retrieval_json),
            "node_latencies": {},
            "query_log_id": log_id,
            "cached": True,
        }

        def cached_stream():
            # A cache hit has nothing to stream, so it emits only the 'done'
            # event; the client renders the message from final_answer when no
            # tokens arrived.
            yield f"event: done\ndata: {json.dumps(cached_payload)}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    _enforce_daily_budget()

    def event_stream():
        answer_parts: list[str] = []

        for event_type, data in stream_chat(
            thread_id=thread_id,
            question=payload.message,
            source_id_filter=payload.source_id_filter,
        ):
            if event_type == "token":
                answer_parts.append(data["text"])
                yield f"event: token\ndata: {json.dumps(data)}\n\n"
                continue

            # data["final_answer"] is authoritative (may have cleaned-up content
            # the raw streamed tokens didn't) - fall back to the raw
            # concatenation only if it's missing for some reason
            full_answer = data.get("final_answer") or "".join(answer_parts)
            _record_turn(
                session, thread_id=thread_id, user=user, question=payload.message, answer=full_answer
            )

            auto_flagged_contribution = None
            detected = data.get("detected_contribution")
            if detected and check_and_record(_client_key(request, user)):
                submission = PendingSubmission(
                    submitted_by_id=user.id,
                    submission_type=SubmissionType(detected["type"]),
                    source_id=payload.source_id_filter or "general",
                    content=detected["content"],
                )
                session.add(submission)
                auto_flagged_contribution = detected["type"]

            session.commit()
            if auto_flagged_contribution:
                notify_new_submission(submission.id, submission.submission_type.value, submission.source_id, submission.content)

            # The streamed 'done' event carries the same fields run_chat
            # returns, so the shared store helper can be reused as-is - this
            # is the write side that keeps the cache filling regardless of
            # which endpoint the UI happens to use.
            _maybe_store_cache(
                session,
                payload,
                cacheable,
                embedding,
                {
                    "answer": full_answer,
                    "sources": data["sources"],
                    "retrieval": data.get("retrieval", []),
                    "answered": data.get("answered", True),
                    "time_sensitive": data.get("time_sensitive", False),
                },
            )

            log_id = _log_query(
                session,
                question=payload.message,
                thread_id=thread_id,
                user=user,
                answered=bool(data.get("answered", True)),
                sources=data["sources"],
                latency_ms=int((time.monotonic() - started) * 1000),
                served_from_cache=False,
            )

            done_payload = {
                "thread_id": thread_id,
                "sources": data["sources"],
                "auto_flagged_contribution": auto_flagged_contribution,
                "final_answer": full_answer,
                "retrieval": data.get("retrieval", []),
                "node_latencies": data.get("node_latencies", {}),
                "query_log_id": log_id,
                "cached": False,
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class FeedbackRequest(BaseModel):
    query_log_id: int
    rating: int  # +1 or -1


@router.post("/feedback", status_code=204)
def rate_answer(
    payload: FeedbackRequest,
    user: User = Depends(get_current_user_or_guest),
    session: Session = Depends(get_session),
):
    """Thumbs up/down on an answer. Deliberately lighter than the knowledge
    submission flow: a one-click signal costs the user nothing, and the
    thumbs-down set becomes a ready-made queue of real failures to turn into
    golden eval cases."""
    if payload.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")

    entry = session.get(QueryLog, payload.query_log_id)
    # You may only rate your own answer. query_log ids are sequential
    # integers, so without the ownership test anyone - including a caller with
    # no token at all - could walk 1..N and thumbs-down every answer in the
    # system, which feeds straight into the admin "rated unhelpful" queue.
    # Answered as 404 rather than 403 so the endpoint does not confirm that
    # some other user's id exists.
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such query")

    entry.rating = payload.rating
    session.commit()


class SubmissionRequest(BaseModel):
    submission_type: str
    source_id: str
    content: str
    related_chunk_id: str | None = None


@router.post("/submissions", status_code=201)
def create_submission(
    request: Request,
    payload: SubmissionRequest,
    user: User = Depends(get_current_user_or_guest),
    session: Session = Depends(get_session),
):
    if not check_and_record(_client_key(request, user)):
        raise HTTPException(status_code=429, detail="Too many submissions - please try again later")

    submission = PendingSubmission(
        submitted_by_id=user.id,
        submission_type=SubmissionType(payload.submission_type),
        source_id=payload.source_id,
        content=payload.content,
        related_chunk_id=payload.related_chunk_id,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    notify_new_submission(submission.id, submission.submission_type.value, submission.source_id, submission.content)
    return {"id": submission.id, "status": submission.status.value}
