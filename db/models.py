import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class SubmissionType(str, enum.Enum):
    NEW_INFO = "new_info"
    CORRECTION = "correction"


class SubmissionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # Was approved and vectorized, then pulled back out of the corpus. Kept
    # distinct from REJECTED so the audit trail still shows the content was
    # live at some point - which matters when tracing an answer a user
    # remembers getting but that the assistant no longer gives.
    REVOKED = "revoked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.USER)
    # An auto-provisioned identity for a visitor who never registered. Each one
    # is its own row so anonymous users get the same isolation as registered
    # ones (own threads, own history, own rate-limit bucket) - they previously
    # all shared a single "guest" account, which made every anonymous
    # conversation part of one indistinguishable pile.
    #
    # Guests hold no usable password and are refused at /auth/login; a token is
    # the only way to act as one.
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    # Bumped by a Telegram user's /new command (see api/telegram_chat.py) to
    # start a fresh LangGraph thread without losing the old one - the thread
    # id includes this, so incrementing it is enough to make the next message
    # begin with no prior context. Unused (stays 0) for anyone who never
    # talks to the bot.
    telegram_thread_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    submissions: Mapped[list["PendingSubmission"]] = relationship(
        foreign_keys="PendingSubmission.submitted_by_id", back_populates="submitted_by"
    )


class PendingSubmission(Base):
    __tablename__ = "pending_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submission_type: Mapped[SubmissionType] = mapped_column(Enum(SubmissionType))
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.PENDING
    )
    source_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    related_chunk_id: Mapped[str | None] = mapped_column(String, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    submitted_by: Mapped["User"] = relationship(foreign_keys=[submitted_by_id])


class ChatMessage(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Course(Base):
    """The course catalog (catalog.csv), as a real relational table - synced
    from the source file at ingestion time (see ingestion/structured_sync.py)
    rather than parsed back out of embedded Chroma chunk text. The catalog is
    still also embedded into Chroma separately (for semantic search over a
    course's skills/description text), but structured lookups (by professor,
    by compulsory flag, ECTS totals) query this table directly."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    ects: Mapped[int] = mapped_column(Integer)
    compulsory: Mapped[bool] = mapped_column(Boolean, default=False)
    offering: Mapped[str | None] = mapped_column(String, nullable=True)
    professor: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    exam_type: Mapped[str | None] = mapped_column(String, nullable=True)


class Deadline(Base):
    """The application deadlines table
    (AEDS_website_application_deadlines_table.md), as a real relational table -
    synced from the source file at ingestion time, same rationale as Course."""

    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_qualification: Mapped[str] = mapped_column(String, index=True)
    starting_semester: Mapped[str] = mapped_column(String)
    first_day: Mapped[str] = mapped_column(String)
    deadline: Mapped[str] = mapped_column(String)


class RuntimeConfig(Base):
    """Single-row table (id=1) holding the subset of settings that are safe to
    change at runtime without a restart or re-ingestion - see
    runtime_config.py. Embedding provider/model and reranker model stay
    config.py constants, since changing those would require re-embedding the
    whole corpus. llm_provider and openrouter_model ARE here (unlike the
    module docstring's older claim) - switching the chat/classifier provider
    needs no re-embedding, only a fresh LLM client, which
    graph/nodes.py's cached getters already re-check on every call."""

    __tablename__ = "runtime_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    llm_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    gemini_model: Mapped[str | None] = mapped_column(String, nullable=True)
    openrouter_model: Mapped[str | None] = mapped_column(String, nullable=True)
    openrouter_fallback_model: Mapped[str | None] = mapped_column(String, nullable=True)
    retrieval_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rerank_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversation_history_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IngestedDocument(Base):
    """Tracks files from the documents folder that have already been embedded,
    so the startup folder scan does not re-ingest unchanged files."""

    __tablename__ = "ingested_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String, unique=True, index=True)
    file_hash: Mapped[str] = mapped_column(String)
    chunk_count: Mapped[int] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Optional freshness metadata, sourced from data/documents/sources.json.
    # valid_until marks content that is knowingly time-bounded (application
    # deadlines are re-published every year) so the admin UI can flag it as
    # expired before the assistant states a stale date with full confidence -
    # a confidently-wrong date is far worse than "I don't know".
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Source-refresh tracking (see scripts/source_refresh.py). Nothing here
    # ever overwrites the curated file above by itself - only an approved
    # source_draft does, and only via api/telegram_bot.py's Approve button.
    # source_text_hash and source_text_snapshot hold the extracted,
    # whitespace-normalised text of the document's source URL as of the last
    # check - hashing bytes was tried first and rejected, because the same
    # source PDF/HTML is NOT byte-stable across two fetches of unchanged
    # content (measured: a 37-byte HTML diff and a re-encoded PDF at
    # identical size), so only the extracted text is a meaningful basis for
    # change detection.
    source_text_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    source_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Word-level diff against the previous snapshot, set only when a change is
    # detected and cleared once an admin dismisses it - this is what the admin
    # review view shows; a curated file is still only ever updated by hand,
    # or via source_draft below.
    source_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    # An LLM-proposed replacement for the curated file, set only for the
    # small AUTO_DRAFT_ELIGIBLE allowlist in scripts/source_refresh.py (where
    # the source URL's whole page maps onto the curated file - not a
    # general auto-curator). Cleared on approve (after being written to disk
    # and re-ingested) or reject (source_diff stays, for the ordinary manual
    # dismiss flow).
    source_draft: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnswerStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CachedAnswer(Base):
    """A question and the answer given for it, reviewed before it is reused.

    This is the system's verified-answer memory rather than a plain cache.
    Every answered question lands here as PENDING and is never served again
    until an admin approves it; the admin may correct the text first, and that
    corrected version is what future askers receive. Rejecting one keeps the
    record (it is evidence of a failure worth turning into an eval case)
    without ever replaying it.

    That gating is the point: generation is not deterministic, so an answer
    that came out wrong once would otherwise be cached and repeated to every
    subsequent student with the same question.

    Only ever populated from, and served to, the first question in a thread:
    a mid-conversation question can depend on earlier turns, so an answer that
    was correct in one thread's context is not safe to replay into another.
    """

    __tablename__ = "cached_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    question_normalized: Mapped[str] = mapped_column(String, index=True)
    embedding: Mapped[str] = mapped_column(Text)  # JSON float array
    answer: Mapped[str] = mapped_column(Text)
    # What the model produced, kept when an admin edits `answer`, so a
    # correction can always be compared against what actually went out.
    original_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    retrieval_json: Mapped[str] = mapped_column(Text, default="[]")
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[AnswerStatus] = mapped_column(
        Enum(AnswerStatus), default=AnswerStatus.PENDING,
        nullable=False, server_default="'PENDING'",
    )
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Which frontend the question came in through: the browser's Origin
    # header for a web caller (e.g. the main site vs. a third-party widget
    # like ECTS Tracker, both allowed by CORS_ALLOW_ORIGINS), "telegram" for
    # the bot, or None if no Origin header was sent at all (a direct API
    # call). Purely informational for the admin review queue - never used
    # for any access-control decision, since it is caller-supplied and not
    # a trust boundary.
    origin: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DailyLlmUsage(Base):
    """One row per calendar day counting LLM requests actually issued.

    Persisted rather than kept in memory because the quota it mirrors is an
    external daily allowance - a process restart must not make the system
    think it has a fresh budget when the provider disagrees.
    """

    __tablename__ = "daily_llm_usage"

    day: Mapped[str] = mapped_column(String, primary_key=True)  # UTC "YYYY-MM-DD"
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class QueryLog(Base):
    """One row per question asked. Exists to answer two product questions that
    nothing else in the system can: which questions do users actually ask, and
    which of those the corpus could NOT answer - the latter being the most
    direct signal of what content is still missing."""

    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # False when the answer looks like a "not covered by the documents"
    # response - see graph/build_graph.py's _looks_unanswered.
    answered: Mapped[bool] = mapped_column(Boolean, default=True)
    source_ids: Mapped[str] = mapped_column(String, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    served_from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    # +1 / -1 from the thumbs control, NULL until the user rates it.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # See CachedAnswer.origin's docstring - same meaning, same caveats.
    origin: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class RateLimitEvent(Base):
    """One row per request that a limiter allowed (see api/rate_limit.py).

    In the database rather than in a process-local dict because the limits are
    meant to bound a person, not a process: with two uvicorn workers, in-memory
    counters give every client twice its allowance, and the exact multiple
    depends on which worker happens to pick up each request. Storing the events
    here makes one shared window regardless of how many workers run.

    Rows are pruned by the limiter itself on every check, so this table stays
    at roughly (active clients x their allowance) rows rather than growing.
    """

    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "{limiter name}:{client key}", e.g. "chat:user:42".
    bucket: Mapped[str] = mapped_column(String, index=True)
    # Unix epoch seconds. Wall clock rather than a monotonic counter, which is
    # only comparable inside one process.
    created_at: Mapped[float] = mapped_column(Float, index=True)


class CorpusVersion(Base):
    """A counter bumped whenever the approved-chunk set changes.

    The BM25 index is rebuilt from Chroma and cached in memory per process. A
    worker that approves a submission can clear its own cache, but it has no
    way to reach into the other workers, which would go on answering from a
    keyword index that no longer matches the corpus. Each worker compares this
    number against the one its cached index was built at, so any change made
    anywhere is picked up everywhere on the next search.
    """

    __tablename__ = "corpus_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


engine = create_engine(f"sqlite:///{settings.sqlite_path}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _record) -> None:
    # WAL mode lets reads proceed without blocking on a concurrent write,
    # which matters here since chat requests read/write chat_history and
    # pending_submissions on every turn.
    dbapi_connection.execute("PRAGMA journal_mode=WAL")
    # Under several workers the rate limiter takes a write lock on every
    # request. Without a busy timeout a request that arrives while another
    # worker holds that lock fails immediately with "database is locked";
    # with one it waits for its turn, which at these volumes is microseconds.
    dbapi_connection.execute("PRAGMA busy_timeout=5000")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _add_missing_columns() -> None:
    """Add columns that exist on the models but not yet in the database file.

    create_all() creates missing TABLES but never alters existing ones, so a
    column added to a model after a database already exists is silently absent
    until something queries it and SQLite raises "no such column". There is no
    migration tool in this project, and for the additive, nullable columns it
    actually uses (see IngestedDocument.valid_until) a one-pass ALTER is
    enough - anything requiring a real backfill or type change would warrant
    bringing in Alembic instead.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all handles brand-new tables
            present = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or column.primary_key:
                    continue
                if not column.nullable and column.server_default is None:
                    # Can't be added to existing rows without a value; leave it
                    # to fail loudly rather than invent one. A Python-side
                    # default() is not enough here - it only applies to rows
                    # this process inserts, never to the ones already on disk.
                    continue
                column_type = column.type.compile(engine.dialect)
                clause = f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}'
                if column.server_default is not None:
                    # Carried through so existing rows get a real value rather
                    # than NULL, which is what makes adding a NOT NULL column
                    # to a populated table work at all.
                    default_sql = column.server_default.arg
                    clause += f" NOT NULL DEFAULT {getattr(default_sql, 'text', default_sql)}"
                connection.execute(text(clause))


def _backfill_guest_flags() -> None:
    """Mark pre-existing anonymous accounts as guests.

    is_guest was added after these rows existed, so the ALTER gave them the
    column default (0) - which would leave the legacy shared guest looking
    like a registered account: rate-limited by user id instead of by IP, and
    still accepting the empty password it was originally created with.
    """
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET is_guest = 1 WHERE email LIKE 'guest%@aeds.local' AND is_guest = 0")
        )


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _backfill_guest_flags()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
