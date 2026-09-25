"""Time-bounded sources: knowing when a document has stopped being current."""

from datetime import date, datetime, timedelta, timezone

from db.freshness import expired_source_ids, is_expired
from db.models import IngestedDocument, SessionLocal
from graph.nodes import _expiry_label


def _seed_document(filename: str, valid_until: datetime | None):
    session = SessionLocal()
    try:
        session.add(
            IngestedDocument(
                filename=filename, file_hash="hash", chunk_count=1, valid_until=valid_until
            )
        )
        session.commit()
    finally:
        session.close()


def test_a_source_without_an_expiry_never_expires():
    assert is_expired(None) is False


def test_expiry_is_read_against_now():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert is_expired(past) is True
    assert is_expired(future) is False


def test_naive_timestamps_are_treated_as_utc():
    # SQLite hands datetimes back without a timezone; reading them as local
    # time would shift the boundary by hours.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    assert is_expired(past) is True


def test_expired_sources_are_keyed_by_source_id_not_filename():
    _seed_document("AEDS_deadlines.md", datetime(2020, 1, 1))
    _seed_document("AEDS_overview.md", None)

    session = SessionLocal()
    try:
        expired = expired_source_ids(session)
    finally:
        session.close()

    # Chunk metadata carries the stem, while the documents table stores the
    # full filename - a mismatch here means the label never attaches.
    assert expired == {"AEDS_deadlines": date(2020, 1, 1)}


def test_only_past_expiries_are_reported():
    _seed_document("future.md", datetime.now(timezone.utc) + timedelta(days=30))

    session = SessionLocal()
    try:
        assert expired_source_ids(session) == {}
    finally:
        session.close()


def _run_generate_with(monkeypatch, docs, expired):
    """Call generate_node with a recording LLM and return the prompt it saw."""
    from langchain_core.messages import AIMessage, HumanMessage

    from graph import nodes

    seen = {}

    class RecordingLlm:
        def invoke(self, messages):
            seen["messages"] = messages
            return AIMessage(content="answer")

    monkeypatch.setattr(nodes, "get_llm", lambda: RecordingLlm())
    monkeypatch.setattr(nodes, "_with_resilience", lambda llm: llm)
    monkeypatch.setattr(nodes, "get_expired_source_ids", lambda: expired)

    nodes.generate_node(
        {"retrieved_docs": docs, "messages": [HumanMessage(content="When is the deadline?")]}
    )
    return "\n".join(str(m.content) for m in seen["messages"])


def test_an_expired_source_reaches_the_model_marked_and_explained(monkeypatch):
    from langchain_core.documents import Document

    prompt = _run_generate_with(
        monkeypatch,
        [Document(page_content="Deadline: 15 July 2026", metadata={"source_id": "deadlines"})],
        {"deadlines": date(2026, 7, 15)},
    )

    assert "OUT OF DATE" in prompt
    # Both halves matter: the inline tag stops a date being quoted away from
    # its caveat, and the instruction tells the model what to do about it.
    assert "already closed" in prompt
    assert "never compute a countdown" in prompt
    assert f"Today's date is {date.today().isoformat()}" in prompt


def test_current_sources_carry_no_staleness_instructions(monkeypatch):
    from langchain_core.documents import Document

    prompt = _run_generate_with(
        monkeypatch,
        [Document(page_content="English B2 is required.", metadata={"source_id": "language"})],
        {},
    )

    assert "OUT OF DATE" not in prompt
    assert "Today's date" not in prompt


def test_the_context_label_names_the_date_content_stopped_being_current():
    expired = {"AEDS_deadlines": date(2026, 7, 15)}

    label = _expiry_label("AEDS_deadlines", expired)
    assert "OUT OF DATE" in label
    assert "2026-07-15" in label
    # A source that is still current must not be labelled, or the model starts
    # hedging on facts that are fine.
    assert _expiry_label("AEDS_overview", expired) == ""
    assert _expiry_label(None, expired) == ""
