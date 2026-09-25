"""Syncs structured source files (catalog.csv, the application deadlines
table) into their real SQLite relational tables (db.models.Course,
db.models.Deadline). Called from ingestion/chunker.py right after a file is
(re-)ingested into Chroma, so the vector store (for semantic search over
course descriptions) and the relational tables (for exact structured lookups -
see ingestion/catalog.py, ingestion/deadlines.py) both stay in sync with the
same source file, instead of the relational side being derived by re-parsing
embedded chunk text."""

import csv
from pathlib import Path

from db.models import Course, Deadline, SessionLocal
from ingestion.deadlines import parse_table_rows

CATALOG_FILENAME = "catalog.csv"
DEADLINES_FILENAME = "AEDS_website_application_deadlines_table.md"


def sync_catalog_to_sql(path: Path) -> int:
    session = SessionLocal()
    try:
        session.query(Course).delete()
        count = 0
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("code") or "").strip()
                name = (row.get("name") or "").strip()
                if not code or not name:
                    continue
                try:
                    ects = int(row.get("ects") or 0)
                except ValueError:
                    ects = 0
                session.add(
                    Course(
                        code=code,
                        name=name,
                        category=(row.get("category") or "other").strip(),
                        ects=ects,
                        compulsory=(row.get("compulsory") or "").strip().lower() == "yes",
                        offering=(row.get("offering") or "").strip() or None,
                        professor=(row.get("professor") or "").strip() or None,
                        language=(row.get("language") or "").strip() or None,
                        exam_type=(row.get("exam_type") or "").strip() or None,
                    )
                )
                count += 1
        session.commit()
        return count
    finally:
        session.close()


def sync_deadlines_to_sql(path: Path) -> int:
    session = SessionLocal()
    try:
        session.query(Deadline).delete()
        text = path.read_text(encoding="utf-8")
        count = 0
        for qualification, starting_semester, first_day, deadline in parse_table_rows(text):
            session.add(
                Deadline(
                    entry_qualification=qualification,
                    starting_semester=starting_semester,
                    first_day=first_day,
                    deadline=deadline,
                )
            )
            count += 1
        session.commit()
        return count
    finally:
        session.close()


def sync_structured_data(path: Path) -> int | None:
    """Returns the number of rows synced, or None if path isn't one of the
    known structured source files (in which case there's nothing to do)."""
    if path.name == CATALOG_FILENAME:
        return sync_catalog_to_sql(path)
    if path.name == DEADLINES_FILENAME:
        return sync_deadlines_to_sql(path)
    return None
