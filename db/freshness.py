"""Which ingested sources have passed their valid_until date.

valid_until is declared per file in data/documents/sources.json and stored on
IngestedDocument at ingest time. Until now it only reached the admin UI, which
meant the assistant would happily quote an application deadline from a cycle
that closed weeks ago, stated with the same confidence as a fact that is still
true. Retrieval cannot filter these chunks out - a closed cycle's dates are
still the best answer available to "when was the deadline" - so instead the
generation step labels them, and the model is told to say so.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path


def is_expired(valid_until: datetime | None, today: date | None = None) -> bool:
    """True when valid_until has passed. Naive values are read as UTC, which is
    how they were written."""
    if valid_until is None:
        return False
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    reference = datetime.now(timezone.utc) if today is None else datetime.combine(
        today, datetime.min.time(), tzinfo=timezone.utc
    )
    return valid_until < reference


def expired_source_ids(session, today: date | None = None) -> dict[str, date]:
    """Map source_id -> the date its content stopped being current.

    Keyed by source_id (the filename stem) because that is what chunk metadata
    carries, while IngestedDocument stores the full filename.
    """
    from db.models import IngestedDocument

    documents = (
        session.query(IngestedDocument)
        .filter(IngestedDocument.valid_until.isnot(None))
        .all()
    )
    return {
        Path(document.filename).stem: document.valid_until.date()
        for document in documents
        if is_expired(document.valid_until, today)
    }


def get_expired_source_ids(today: date | None = None) -> dict[str, date]:
    """Session-owning wrapper for callers outside the request cycle (the graph
    nodes), mirroring how ingestion/deadlines.py reads its own table."""
    from db.models import SessionLocal

    session = SessionLocal()
    try:
        return expired_source_ids(session, today)
    finally:
        session.close()
