"""Shared helper for reading the structured course catalog (catalog.csv) back
out as plain Python dicts - used by both the chat assistant's curriculum-
listing shortcut and the study plan recommender. Queried from the Course SQL
table (see db.models.Course), which ingestion/structured_sync.py keeps in sync
with catalog.csv every time it's (re-)ingested, rather than re-parsed out of
embedded Chroma chunk text on every call."""

from db.models import Course, SessionLocal


def get_catalog_courses() -> list[dict]:
    """Every course in the catalog as a dict with at least: category, code,
    name, ects (int), compulsory (bool), offering, professor."""
    session = SessionLocal()
    try:
        return [
            {
                "category": course.category,
                "code": course.code,
                "name": course.name,
                "ects": course.ects,
                "compulsory": course.compulsory,
                "offering": course.offering,
                "professor": course.professor,
                "language": course.language,
            }
            for course in session.query(Course).all()
        ]
    finally:
        session.close()
