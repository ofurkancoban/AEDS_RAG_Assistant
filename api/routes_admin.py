import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import llm_budget
from api.auth import hash_password, require_admin
from api.content_flags import injection_markers
from api.routes_auth import MIN_PASSWORD_LENGTH, _normalise_email
from config import settings
from db.chroma_client import (
    delete_chunks_by_submission_id,
    get_corpus_stats,
    get_embedding_dimension,
    mark_deprecated,
    restore_chunk,
)
from db.models import (
    AnswerStatus,
    CachedAnswer,
    ChatMessage,
    IngestedDocument,
    PendingSubmission,
    QueryLog,
    Role,
    SubmissionStatus,
    User,
    get_session,
)
from ingestion.chunker import (
    SUPPORTED_EXTENSIONS,
    delete_ingested_document,
    ingest_and_record_file,
    ingest_approved_submission,
)
from graph.nodes import SYSTEM_PROMPT
from runtime_config import (
    ALLOWED_GEMINI_MODELS,
    ALLOWED_LLM_PROVIDERS,
    active_chat_model,
    get_runtime_config,
    update_runtime_config,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class SubmissionOut(BaseModel):
    id: int
    submission_type: str
    status: str
    source_id: str
    content: str
    related_chunk_id: str | None
    created_at: datetime
    # Patterns suggesting the text is addressed to the model rather than to a
    # reader. Advisory only: approving is still a human decision, and this is
    # here so the decision is an informed one.
    injection_markers: list[str] = []

    class Config:
        from_attributes = True


def _to_submission_out(row: PendingSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        submission_type=row.submission_type.value,
        status=row.status.value,
        source_id=row.source_id,
        content=row.content,
        related_chunk_id=row.related_chunk_id,
        created_at=row.created_at,
        injection_markers=injection_markers(row.content),
    )


@router.get("/pending", response_model=list[SubmissionOut])
def list_pending(
    status_filter: str = "pending",
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """status_filter: 'pending' (default), 'approved', 'rejected', 'revoked',
    or 'all' - lets the Admin Review UI show reviewed history, not just the
    open queue."""
    query = session.query(PendingSubmission)
    if status_filter != "all":
        try:
            query = query.filter(PendingSubmission.status == SubmissionStatus(status_filter))
        except ValueError:
            allowed = ", ".join(s.value for s in SubmissionStatus)
            raise HTTPException(status_code=400, detail=f"status_filter must be one of: {allowed}, all")

    submissions = query.order_by(PendingSubmission.created_at.desc()).all()
    return [_to_submission_out(row) for row in submissions]


class ReviewRequest(BaseModel):
    admin_note: str | None = None


class SubmissionUpdateRequest(BaseModel):
    content: str
    source_id: str


@router.put("/pending/{submission_id}", response_model=SubmissionOut)
def update_submission(
    submission_id: int,
    payload: SubmissionUpdateRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Lets an admin correct a user submission's content/category before
    approving it - e.g. fixing a typo or splitting a vague claim into a
    precise one - without having to reject and ask the user to resubmit."""
    submission = session.get(PendingSubmission, submission_id)
    if submission is None or submission.status != SubmissionStatus.PENDING:
        raise HTTPException(status_code=404, detail="Submission not found or already reviewed")

    submission.content = payload.content
    submission.source_id = payload.source_id
    session.commit()
    session.refresh(submission)
    return _to_submission_out(submission)


@router.post("/pending/{submission_id}/approve")
def approve_submission(
    submission_id: int,
    payload: ReviewRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    submission = session.get(PendingSubmission, submission_id)
    if submission is None or submission.status != SubmissionStatus.PENDING:
        raise HTTPException(status_code=404, detail="Submission not found or already reviewed")

    if submission.submission_type.value == "correction" and submission.related_chunk_id:
        mark_deprecated(submission.related_chunk_id)

    new_chunk_id = ingest_approved_submission(
        content=submission.content,
        source_id=submission.source_id,
        submission_id=submission.id,
    )

    submission.status = SubmissionStatus.APPROVED
    submission.admin_note = payload.admin_note
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = admin.id
    session.commit()

    return {"id": submission.id, "status": "approved", "new_chunk_id": new_chunk_id}


@router.post("/pending/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    payload: ReviewRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    submission = session.get(PendingSubmission, submission_id)
    if submission is None or submission.status != SubmissionStatus.PENDING:
        raise HTTPException(status_code=404, detail="Submission not found or already reviewed")

    submission.status = SubmissionStatus.REJECTED
    submission.admin_note = payload.admin_note
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = admin.id
    session.commit()

    return {"id": submission.id, "status": "rejected"}


@router.post("/pending/{submission_id}/revoke")
def revoke_submission(
    submission_id: int,
    payload: ReviewRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Pull an already-approved submission back out of the corpus.

    Approval is the one admin action that was irreversible: it embeds the
    content as a chunk that no other screen can reach (delete_document only
    covers file-backed documents), so a mistakenly approved fact kept being
    cited with no way to take it back short of editing the vector store by
    hand.
    """
    submission = session.get(PendingSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status != SubmissionStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Only approved submissions can be revoked (this one is {submission.status.value})",
        )

    deleted = delete_chunks_by_submission_id(submission.id)

    # Approving a correction deprecates the chunk it superseded; undo that too,
    # or revoking would leave the original hidden and the correction gone -
    # removing content from the corpus that nobody asked to remove.
    restored = False
    if submission.submission_type.value == "correction" and submission.related_chunk_id:
        restored = restore_chunk(submission.related_chunk_id)

    submission.status = SubmissionStatus.REVOKED
    submission.admin_note = payload.admin_note
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = admin.id
    session.commit()

    return {
        "id": submission.id,
        "status": "revoked",
        "chunks_deleted": deleted,
        "original_chunk_restored": restored,
    }


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Validates before writing, and un-writes on failure.

    The previous version wrote the upload to documents_dir first and ingested
    second, so an unsupported or unparseable file left an orphan behind in the
    corpus directory forever while the admin only saw an opaque 500.
    """
    # Path(...).name strips any directory component: an uploaded filename is
    # attacker-controlled, and "../../x" would otherwise escape documents_dir.
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="Upload has no filename")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix or filename}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail=f"'{filename}' is empty - nothing to ingest")

    destination = settings.documents_dir / filename
    existed_before = destination.exists()
    previous_bytes = destination.read_bytes() if existed_before else None
    destination.write_bytes(contents)

    try:
        chunk_count = ingest_and_record_file(destination, session)
    except Exception as exc:
        # Restore whatever was there so a failed re-upload cannot destroy an
        # already-indexed document, and drop the file entirely if it is new.
        if previous_bytes is None:
            destination.unlink(missing_ok=True)
        else:
            destination.write_bytes(previous_bytes)
        raise HTTPException(status_code=400, detail=f"Could not ingest '{filename}': {exc}") from exc

    if chunk_count is None:
        # Content hash matched an already-ingested file: correctly skipped, not
        # an error. Reported distinctly so the UI can say "unchanged" instead of
        # claiming a successful ingest of 0 chunks.
        existing = (
            session.query(IngestedDocument).filter(IngestedDocument.filename == filename).first()
        )
        return {
            "filename": filename,
            "chunks_ingested": existing.chunk_count if existing else 0,
            "unchanged": True,
        }

    if chunk_count == 0:
        # A supported type that yielded no text at all (e.g. a scanned PDF with
        # no text layer) - indistinguishable from success to the admin
        # otherwise, since the document would just never be retrievable.
        if previous_bytes is None:
            destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"'{filename}' produced no extractable text - it was not indexed",
        )

    return {"filename": filename, "chunks_ingested": chunk_count, "unchanged": False}


class IngestedDocumentOut(BaseModel):
    filename: str
    chunk_count: int
    ingested_at: datetime
    valid_until: datetime | None = None
    expired: bool = False

    class Config:
        from_attributes = True


def _is_expired(document: IngestedDocument) -> bool:
    if document.valid_until is None:
        return False
    valid_until = document.valid_until
    if valid_until.tzinfo is None:
        # SQLite hands datetimes back naive; the values were stored as UTC.
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    return valid_until < datetime.now(timezone.utc)


@router.get("/documents", response_model=list[IngestedDocumentOut])
def list_documents(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    documents = (
        session.query(IngestedDocument)
        .order_by(IngestedDocument.ingested_at.desc())
        .all()
    )
    return [
        IngestedDocumentOut(
            filename=d.filename,
            chunk_count=d.chunk_count,
            ingested_at=d.ingested_at,
            valid_until=d.valid_until,
            expired=_is_expired(d),
        )
        for d in documents
    ]


class SourceChangeOut(BaseModel):
    filename: str
    url: str | None = None
    last_checked_at: datetime | None = None
    last_changed_at: datetime
    diff: str


@router.get("/source-changes", response_model=list[SourceChangeOut])
def list_source_changes(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Sources scripts/source_refresh.py found changed since it last checked
    them, most recent first. Detect-only: nothing here has touched the
    curated file - an admin decides by hand whether to re-curate it."""
    from ingestion.chunker import load_source_urls

    urls = load_source_urls()
    documents = (
        session.query(IngestedDocument)
        .filter(IngestedDocument.source_diff.isnot(None))
        .order_by(IngestedDocument.last_changed_at.desc())
        .all()
    )
    return [
        SourceChangeOut(
            filename=d.filename,
            url=urls.get(d.filename),
            last_checked_at=d.last_checked_at,
            last_changed_at=d.last_changed_at,
            diff=d.source_diff,
        )
        for d in documents
    ]


@router.post("/source-changes/{filename}/dismiss")
def dismiss_source_change(
    filename: str,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Clears the flagged diff once an admin has reviewed it (and re-curated
    the file by hand, if warranted). last_changed_at is left as-is - it stays
    a record of when the source last moved, it just stops showing as pending."""
    existing = session.query(IngestedDocument).filter(IngestedDocument.filename == filename).first()
    if existing is None or existing.source_diff is None:
        raise HTTPException(status_code=404, detail="No pending source change for that filename")
    existing.source_diff = None
    session.commit()
    return {"filename": filename, "status": "dismissed"}


@router.delete("/documents/{filename}")
def delete_document(
    filename: str,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    deleted = delete_ingested_document(filename, session)
    if not deleted:
        raise HTTPException(status_code=404, detail="No ingested document with that filename")
    return {"filename": filename, "status": "deleted"}


class AnswerOut(BaseModel):
    id: int
    question: str
    answer: str
    original_answer: str | None
    status: str
    edited: bool
    sources: list[str]
    hit_count: int
    admin_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    # Computed over the question and the answer together: either half can
    # carry the instruction that produced the other.
    injection_markers: list[str] = []
    # Which frontend this came in through - see CachedAnswer.origin's
    # docstring. None for anything answered before this field existed.
    origin: str | None = None


def _to_answer_out(row: CachedAnswer) -> AnswerOut:
    sources = sorted({s.get("source_id", "") for s in json.loads(row.sources_json or "[]")})
    return AnswerOut(
        id=row.id,
        question=row.question,
        answer=row.answer,
        original_answer=row.original_answer,
        status=row.status.value,
        # True once an admin has rewritten what the model said, which is the
        # difference between "checked and fine" and "checked and corrected".
        edited=bool(row.original_answer) and row.original_answer != row.answer,
        sources=[s for s in sources if s],
        hit_count=row.hit_count,
        admin_note=row.admin_note,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
        injection_markers=injection_markers(f"{row.question}\n{row.answer}"),
        origin=row.origin,
    )


@router.get("/answers", response_model=list[AnswerOut])
def list_answers(
    status_filter: str = "pending",
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """The answer review queue.

    Every question a student asks is recorded with the answer that was given,
    and stays unusable until reviewed. Approving one makes it the reply future
    askers get for the same question; rejecting keeps the record without ever
    serving it again.
    """
    query = session.query(CachedAnswer)
    if status_filter != "all":
        try:
            query = query.filter(CachedAnswer.status == AnswerStatus(status_filter))
        except ValueError:
            allowed = ", ".join(s.value for s in AnswerStatus)
            raise HTTPException(status_code=400, detail=f"status_filter must be one of: {allowed}, all")
    rows = query.order_by(CachedAnswer.created_at.desc()).limit(300).all()
    return [_to_answer_out(r) for r in rows]


class AnswerReviewRequest(BaseModel):
    # A corrected answer to store in place of the model's. Omit to approve the
    # answer as generated.
    answer: str | None = None
    admin_note: str | None = None


@router.post("/answers/{answer_id}/approve", response_model=AnswerOut)
def approve_answer(
    answer_id: int,
    payload: AnswerReviewRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    row = session.get(CachedAnswer, answer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such answer")

    if payload.answer is not None and payload.answer.strip():
        if not row.original_answer:
            row.original_answer = row.answer
        row.answer = payload.answer.strip()

    row.status = AnswerStatus.APPROVED
    row.admin_note = payload.admin_note
    row.reviewed_at = datetime.now(timezone.utc)
    row.reviewed_by_id = admin.id
    session.commit()
    session.refresh(row)
    return _to_answer_out(row)


@router.post("/answers/{answer_id}/reject", response_model=AnswerOut)
def reject_answer(
    answer_id: int,
    payload: AnswerReviewRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Mark an answer as wrong. The row stays: a question the assistant got
    wrong is the most useful thing there is to turn into a regression case."""
    row = session.get(CachedAnswer, answer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such answer")

    row.status = AnswerStatus.REJECTED
    row.admin_note = payload.admin_note
    row.reviewed_at = datetime.now(timezone.utc)
    row.reviewed_by_id = admin.id
    session.commit()
    session.refresh(row)
    return _to_answer_out(row)


@router.delete("/answers/{answer_id}")
def delete_answer(
    answer_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    row = session.get(CachedAnswer, answer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such answer")
    session.delete(row)
    session.commit()
    return {"id": answer_id, "status": "deleted"}


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime
    # Counts of what the account has done, so an admin can see whether a row is
    # a dormant leftover or has real activity behind it before removing it.
    submissions: int
    reviews: int


class UserListOut(BaseModel):
    users: list[UserOut]
    # Anonymous visitors are counted, never listed: there is nothing
    # identifying to show, and on a live deployment there would be thousands.
    anonymous_sessions: int


def _staff_query(session: Session):
    return session.query(User).filter(User.is_guest.is_(False))


def _admin_count(session: Session) -> int:
    return _staff_query(session).filter(User.role == Role.ADMIN).count()


def _to_user_out(session: Session, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role.value,
        created_at=user.created_at,
        submissions=session.query(PendingSubmission)
        .filter(PendingSubmission.submitted_by_id == user.id)
        .count(),
        reviews=session.query(PendingSubmission)
        .filter(PendingSubmission.reviewed_by_id == user.id)
        .count(),
    )


def _load_staff_account(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="No such account")
    if user.is_guest:
        # Guests authenticate by token only and hold an unusable password hash;
        # exposing them to account management would contradict that.
        raise HTTPException(
            status_code=400, detail="That is an anonymous session, not a staff account"
        )
    return user


@router.get("/users", response_model=UserListOut)
def list_users(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Staff accounts only.

    Public registration is closed - people using the assistant stay anonymous -
    so every row here is someone given access deliberately.
    """
    return UserListOut(
        users=[_to_user_out(session, u) for u in _staff_query(session).order_by(User.id).all()],
        anonymous_sessions=session.query(User).filter(User.is_guest.is_(True)).count(),
    )


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreateRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if payload.role not in (Role.ADMIN.value, Role.USER.value):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'user'")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )

    email = _normalise_email(payload.email)
    if session.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        role=Role(payload.role),
        is_guest=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _to_user_out(session, user)


class UserUpdateRequest(BaseModel):
    role: str | None = None
    password: str | None = None


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    user = _load_staff_account(session, user_id)

    if payload.password is not None:
        if len(payload.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        user.hashed_password = hash_password(payload.password)

    if payload.role is not None:
        if payload.role not in (Role.ADMIN.value, Role.USER.value):
            raise HTTPException(status_code=400, detail="role must be 'admin' or 'user'")
        losing_admin = user.role == Role.ADMIN and payload.role != Role.ADMIN.value
        if losing_admin:
            if user.id == admin.id:
                # Otherwise an admin can lock themselves out mid-session with
                # no way back except the command line.
                raise HTTPException(status_code=400, detail="You cannot remove your own admin access")
            if _admin_count(session) <= 1:
                raise HTTPException(
                    status_code=400, detail="This is the last admin - promote someone else first"
                )
        user.role = Role(payload.role)

    session.commit()
    session.refresh(user)
    return _to_user_out(session, user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Remove a staff account, keeping the record of what it reviewed.

    SQLite does not enforce foreign keys here, so a plain delete would leave
    submissions and logs pointing at a row that no longer exists. Each
    reference is therefore handled explicitly rather than left dangling.
    """
    user = _load_staff_account(session, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.role == Role.ADMIN and _admin_count(session) <= 1:
        raise HTTPException(
            status_code=400, detail="This is the last admin - promote someone else first"
        )

    submitted = (
        session.query(PendingSubmission)
        .filter(PendingSubmission.submitted_by_id == user.id)
        .count()
    )
    if submitted:
        # submitted_by_id is NOT NULL, so there is nowhere to move these to
        # without inventing an owner. Demoting keeps the trail intact.
        raise HTTPException(
            status_code=400,
            detail=(
                f"This account submitted {submitted} knowledge item(s), which would lose their "
                "author. Change the role to 'user' instead of deleting it."
            ),
        )

    # Reviews stay, de-attributed: the decision still happened.
    session.query(PendingSubmission).filter(PendingSubmission.reviewed_by_id == user.id).update(
        {"reviewed_by_id": None}, synchronize_session=False
    )
    # Questions stay for the content-gap analytics but stop being linked to a
    # person; their own chat transcript is theirs and goes with the account.
    session.query(QueryLog).filter(QueryLog.user_id == user.id).update(
        {"user_id": None}, synchronize_session=False
    )
    session.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete(
        synchronize_session=False
    )

    email = user.email
    session.delete(user)
    session.commit()
    return {"id": user_id, "email": email, "status": "deleted"}


class ConfigField(BaseModel):
    value: object
    read_only: bool
    note: str | None = None


class ConfigOut(BaseModel):
    chat_model: ConfigField
    default_system_prompt: ConfigField
    # llm_provider IS live-editable - graph/nodes.py, api/rate_limit.py and
    # llm_budget.py all re-check it against the live value on every call, no
    # restart needed (see runtime_config.py's module docstring).
    llm_provider: ConfigField
    gemini_model: ConfigField
    openrouter_model: ConfigField
    openrouter_fallback_model: ConfigField
    retrieval_top_k: ConfigField
    rerank_top_k: ConfigField
    conversation_history_window: ConfigField
    system_prompt_override: ConfigField
    # Read-only, informational - changing these would require re-embedding the
    # whole corpus, which nothing here does live.
    embedding_provider: ConfigField
    embedding_model: ConfigField
    reranker_model: ConfigField
    chunk_size: ConfigField
    chunk_overlap: ConfigField


@router.get("/config", response_model=ConfigOut)
def get_config(admin: User = Depends(require_admin)):
    runtime = get_runtime_config()
    embedding_model = (
        settings.local_embedding_model
        if settings.embedding_provider == "local"
        else settings.gemini_embedding_model
        if settings.embedding_provider == "gemini"
        else settings.ollama_embedding_model
    )
    serves_gemini = runtime.llm_provider == "gemini"
    serves_openrouter = runtime.llm_provider == "openrouter"
    keyed_providers = [
        p
        for p in ALLOWED_LLM_PROVIDERS
        if p == "ollama" or (p == "gemini" and settings.gemini_api_key) or (p == "openrouter" and settings.openrouter_api_key)
    ]
    return ConfigOut(
        # The model actually answering, whichever provider is active. Without
        # this the UI showed gemini_model unconditionally, i.e. the name of a
        # model that is not running whenever llm_provider is "ollama".
        chat_model=ConfigField(value=active_chat_model(), read_only=True),
        # The prompt actually in force when no override is set. Exposed because
        # the override box is otherwise an empty field asking the admin to
        # replace something they have no way to read.
        default_system_prompt=ConfigField(
            value=SYSTEM_PROMPT,
            read_only=True,
            note="In use whenever the override below is empty",
        ),
        llm_provider=ConfigField(
            value=runtime.llm_provider,
            read_only=False,
            note=(
                f"Allowed: {', '.join(ALLOWED_LLM_PROVIDERS)}. Only providers with a key "
                f"configured in .env can be switched to: {', '.join(keyed_providers)}. "
                "Takes effect on the next chat turn, no restart needed."
            ),
        ),
        gemini_model=ConfigField(
            value=runtime.gemini_model,
            # Editable only when Gemini is the active provider; otherwise the
            # setting is stored but never consulted, so offering it as a live
            # control is a lie.
            read_only=not serves_gemini,
            note=(
                f"Allowed: {', '.join(ALLOWED_GEMINI_MODELS)}"
                if serves_gemini
                else f"Not in use - llm_provider is '{runtime.llm_provider}', "
                f"serving {active_chat_model()}. Set llm_provider to 'gemini' to enable."
            ),
        ),
        openrouter_model=ConfigField(
            value=runtime.openrouter_model,
            read_only=not serves_openrouter,
            note=(
                "Any OpenRouter model id, e.g. google/gemma-4-31b-it:free - see "
                "https://openrouter.ai/api/v1/models for free (':free' suffixed) ones. "
                "No allowlist here, unlike gemini_model: OpenRouter's catalog changes "
                "too often to hardcode."
                if serves_openrouter
                else f"Not in use - llm_provider is '{runtime.llm_provider}', "
                f"serving {active_chat_model()}. Set llm_provider to 'openrouter' to enable."
            ),
        ),
        openrouter_fallback_model=ConfigField(
            value=runtime.openrouter_fallback_model,
            read_only=not serves_openrouter,
            note=(
                "Tried only if openrouter_model's own call fails - protects against a "
                "'stealth' (anonymous, temporary) model being pulled or erroring with no "
                "notice. Empty disables the fallback. Note: any ':free' model, including "
                "this one, can itself be rate-limited by OpenRouter's shared upstream pool "
                "at any given moment - this is a mitigation, not a guarantee."
                if serves_openrouter
                else f"Not in use - llm_provider is '{runtime.llm_provider}', "
                f"serving {active_chat_model()}. Set llm_provider to 'openrouter' to enable."
            ),
        ),
        retrieval_top_k=ConfigField(value=runtime.retrieval_top_k, read_only=False),
        rerank_top_k=ConfigField(value=runtime.rerank_top_k, read_only=False),
        conversation_history_window=ConfigField(value=runtime.conversation_history_window, read_only=False),
        system_prompt_override=ConfigField(
            value=runtime.system_prompt_override,
            read_only=False,
            note=(
                "Empty means the default above is used - this field holds a replacement, "
                "not a copy of the active prompt"
            ),
        ),
        embedding_provider=ConfigField(
            value=settings.embedding_provider,
            read_only=True,
            note="Changing this requires wiping and re-embedding the whole corpus - not live-editable",
        ),
        embedding_model=ConfigField(value=embedding_model, read_only=True),
        reranker_model=ConfigField(value=settings.reranker_model, read_only=True),
        chunk_size=ConfigField(
            value=settings.chunk_size,
            read_only=True,
            note="Only affects documents ingested from now on, not already-embedded chunks",
        ),
        chunk_overlap=ConfigField(value=settings.chunk_overlap, read_only=True),
    )


class ConfigUpdateRequest(BaseModel):
    llm_provider: str | None = None
    gemini_model: str | None = None
    openrouter_model: str | None = None
    openrouter_fallback_model: str | None = None
    retrieval_top_k: int | None = None
    rerank_top_k: int | None = None
    conversation_history_window: int | None = None
    system_prompt_override: str | None = None
    reset_system_prompt: bool = False


# Upper bounds mirror the admin UI's slider ranges. They matter because the
# API is the real contract: without them a direct PUT could set
# retrieval_top_k to 100000 on a few-hundred-chunk corpus, making every
# subsequent query rerank the entire collection.
MAX_RETRIEVAL_TOP_K = 30
MAX_RERANK_TOP_K = 10
MAX_HISTORY_WINDOW = 30


@router.put("/config", response_model=ConfigOut)
def put_config(payload: ConfigUpdateRequest, admin: User = Depends(require_admin)):
    runtime = get_runtime_config()

    # The provider this request ends up with, whether or not llm_provider is
    # part of the payload - gemini_model/openrouter_model's own editability
    # checks below must agree with a provider switch made in the SAME
    # request, not just the one already in force.
    effective_provider = payload.llm_provider if payload.llm_provider is not None else runtime.llm_provider

    if payload.llm_provider is not None:
        if payload.llm_provider not in ALLOWED_LLM_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"llm_provider must be one of: {', '.join(ALLOWED_LLM_PROVIDERS)}",
            )
        if payload.llm_provider == "gemini" and not settings.gemini_api_key:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to 'gemini': GEMINI_API_KEY is not set in .env.",
            )
        if payload.llm_provider == "openrouter" and not settings.openrouter_api_key:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to 'openrouter': OPENROUTER_API_KEY is not set in .env.",
            )

    if payload.gemini_model is not None:
        if effective_provider != "gemini":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"gemini_model is not editable while llm_provider is "
                    f"'{effective_provider}' - set llm_provider to 'gemini' first "
                    "(in the same request, if you like)."
                ),
            )
        if payload.gemini_model not in ALLOWED_GEMINI_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"gemini_model must be one of: {', '.join(ALLOWED_GEMINI_MODELS)}",
            )

    if payload.openrouter_model is not None:
        if effective_provider != "openrouter":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"openrouter_model is not editable while llm_provider is "
                    f"'{effective_provider}' - set llm_provider to 'openrouter' first "
                    "(in the same request, if you like)."
                ),
            )
        if not payload.openrouter_model.strip():
            raise HTTPException(status_code=400, detail="openrouter_model cannot be empty.")

    if payload.openrouter_fallback_model is not None:
        if effective_provider != "openrouter":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"openrouter_fallback_model is not editable while llm_provider is "
                    f"'{effective_provider}' - set llm_provider to 'openrouter' first "
                    "(in the same request, if you like)."
                ),
            )
        # Empty is allowed here (unlike openrouter_model) - it's the documented
        # way to disable the fallback entirely (see _with_fallback in graph/nodes.py).

    if payload.retrieval_top_k is not None and not 1 <= payload.retrieval_top_k <= MAX_RETRIEVAL_TOP_K:
        raise HTTPException(
            status_code=400, detail=f"retrieval_top_k must be between 1 and {MAX_RETRIEVAL_TOP_K}"
        )
    if payload.rerank_top_k is not None and not 1 <= payload.rerank_top_k <= MAX_RERANK_TOP_K:
        raise HTTPException(
            status_code=400, detail=f"rerank_top_k must be between 1 and {MAX_RERANK_TOP_K}"
        )
    if payload.conversation_history_window is not None and not 0 <= payload.conversation_history_window <= MAX_HISTORY_WINDOW:
        raise HTTPException(
            status_code=400,
            detail=f"conversation_history_window must be between 0 and {MAX_HISTORY_WINDOW}",
        )

    # Reranking can only narrow the retrieved pool, so a rerank_top_k above
    # retrieval_top_k silently does nothing - reject it rather than let the
    # admin believe they widened the LLM's context.
    effective_retrieval = (
        payload.retrieval_top_k if payload.retrieval_top_k is not None else runtime.retrieval_top_k
    )
    effective_rerank = (
        payload.rerank_top_k if payload.rerank_top_k is not None else runtime.rerank_top_k
    )
    if effective_rerank > effective_retrieval:
        raise HTTPException(
            status_code=400,
            detail=(
                f"rerank_top_k ({effective_rerank}) cannot exceed retrieval_top_k "
                f"({effective_retrieval}) - reranking only narrows the retrieved pool"
            ),
        )

    fields = {}
    if payload.llm_provider is not None:
        fields["llm_provider"] = payload.llm_provider
    if payload.gemini_model is not None:
        fields["gemini_model"] = payload.gemini_model
    if payload.openrouter_model is not None:
        fields["openrouter_model"] = payload.openrouter_model
    if payload.openrouter_fallback_model is not None:
        fields["openrouter_fallback_model"] = payload.openrouter_fallback_model
    if payload.retrieval_top_k is not None:
        fields["retrieval_top_k"] = payload.retrieval_top_k
    if payload.rerank_top_k is not None:
        fields["rerank_top_k"] = payload.rerank_top_k
    if payload.conversation_history_window is not None:
        fields["conversation_history_window"] = payload.conversation_history_window
    if payload.reset_system_prompt:
        fields["system_prompt_override"] = None
    elif payload.system_prompt_override is not None:
        fields["system_prompt_override"] = payload.system_prompt_override

    update_runtime_config(**fields)
    return get_config(admin)


class StatsOut(BaseModel):
    total_chunks: int
    total_sources: int
    embedding_dimension: int
    embedding_model: str
    reranker_model: str
    llm_model: str
    llm_provider: str
    pending_submissions: int
    pending_answers: int
    expired_documents: int
    llm_calls_today: int
    llm_daily_budget: int
    pending_source_changes: int


@router.get("/stats", response_model=StatsOut)
def get_stats(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    corpus = get_corpus_stats()
    embedding_model = (
        settings.local_embedding_model
        if settings.embedding_provider == "local"
        else settings.gemini_embedding_model
        if settings.embedding_provider == "gemini"
        else settings.ollama_embedding_model
    )
    pending_count = (
        session.query(PendingSubmission).filter(PendingSubmission.status == SubmissionStatus.PENDING).count()
    )
    expired = sum(1 for d in session.query(IngestedDocument).all() if _is_expired(d))
    return StatsOut(
        total_chunks=corpus["total_chunks"],
        total_sources=corpus["total_sources"],
        embedding_dimension=get_embedding_dimension(),
        embedding_model=embedding_model,
        reranker_model=settings.reranker_model,
        llm_model=active_chat_model(),
        llm_provider=settings.llm_provider,
        pending_submissions=pending_count,
        pending_answers=session.query(CachedAnswer)
        .filter(CachedAnswer.status == AnswerStatus.PENDING)
        .count(),
        expired_documents=expired,
        llm_calls_today=llm_budget.usage_today(),
        llm_daily_budget=settings.effective_daily_llm_budget,
        pending_source_changes=session.query(IngestedDocument)
        .filter(IngestedDocument.source_diff.isnot(None))
        .count(),
    )


class QuestionCount(BaseModel):
    question: str
    count: int


class AnalyticsOut(BaseModel):
    total_queries: int
    unanswered_queries: int
    cache_hit_rate: float
    thumbs_up: int
    thumbs_down: int
    avg_latency_ms: int
    top_questions: list[QuestionCount]
    content_gaps: list[QuestionCount]
    thumbs_down_questions: list[str]


@router.get("/analytics", response_model=AnalyticsOut)
def get_analytics(
    days: int = 30,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Usage analytics over the last N days.

    content_gaps is the point of this endpoint: questions users asked that the
    corpus could not answer, ranked by frequency. That list is the most direct
    evidence available of which documents are still missing - far better than
    guessing at what students might want.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.query(QueryLog).filter(QueryLog.created_at >= since).all()

    if not rows:
        return AnalyticsOut(
            total_queries=0,
            unanswered_queries=0,
            cache_hit_rate=0.0,
            thumbs_up=0,
            thumbs_down=0,
            avg_latency_ms=0,
            top_questions=[],
            content_gaps=[],
            thumbs_down_questions=[],
        )

    def _ranked(entries: list[QueryLog], limit: int = 10) -> list[QuestionCount]:
        counter = Counter(r.question.strip() for r in entries)
        return [QuestionCount(question=q, count=c) for q, c in counter.most_common(limit)]

    unanswered = [r for r in rows if not r.answered]
    cache_hits = sum(1 for r in rows if r.served_from_cache)
    # Cache hits are excluded from the latency average: they are sub-second by
    # construction and would otherwise mask how slow real pipeline runs are.
    live = [r for r in rows if not r.served_from_cache]

    return AnalyticsOut(
        total_queries=len(rows),
        unanswered_queries=len(unanswered),
        cache_hit_rate=round(cache_hits / len(rows), 3),
        thumbs_up=sum(1 for r in rows if r.rating == 1),
        thumbs_down=sum(1 for r in rows if r.rating == -1),
        avg_latency_ms=int(sum(r.latency_ms for r in live) / len(live)) if live else 0,
        top_questions=_ranked(rows),
        content_gaps=_ranked(unanswered),
        thumbs_down_questions=[r.question for r in rows if r.rating == -1][:20],
    )
