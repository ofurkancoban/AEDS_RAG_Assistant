"""Fetches the AEDS_ECTS_Tracker project's anonymous course-difficulty
ratings (ratings.json, code -> {count, sum}, 1 easiest - 5 hardest) and syncs
them onto the matching Course rows here, so graph/nodes.py's schedule
recommender can prefer easier electives when there's a genuine choice among
several that all satisfy a category's remaining ECTS target - the ratings
themselves are collected in that project, not this one.

Stdlib only, mirroring scripts/fetch_catalog.py's own fetch convention, so
this can run the same way in the same nightly cron slot (see
scripts/update_ratings.py)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from db.models import Course, SessionLocal

RATINGS_URL = "https://raw.githubusercontent.com/ofurkancoban/AEDS_ECTS_Tracker/main/ratings.json"
USER_AGENT = "AEDS-RAG-Assistant ratings sync (github.com/ofurkancoban)"


def fetch_ratings(url: str = RATINGS_URL) -> dict[str, dict]:
    """{code: {"count": int, "sum": int}, ...} straight off the tracker's
    ratings.json. Raises on a network error or malformed response - callers
    decide whether that should block a sync run or just be logged, same as
    fetch_catalog.py's own fetch() leaves retry/failure handling to its
    caller."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object from {url}, got {type(data).__name__}")
    return data


def sync_ratings_to_sql(ratings: dict[str, dict]) -> int:
    """Updates difficulty_avg/difficulty_count on existing Course rows by
    code - never inserts new rows (a rating for a code the catalog doesn't
    have is simply not this table's concern) and never deletes the whole
    table first (unlike sync_catalog_to_sql: ratings.json's vote counts only
    ever grow, so a fetch that failed or returned a stale snapshot should
    leave the last-known-good numbers in place rather than wiping them).
    Returns how many Course rows were actually updated."""
    session = SessionLocal()
    try:
        updated = 0
        courses_by_code = {c.code.lower(): c for c in session.query(Course).all()}
        for code, entry in ratings.items():
            course = courses_by_code.get(code.strip().lower())
            if course is None:
                continue
            count = entry.get("count")
            total = entry.get("sum")
            if not isinstance(count, int) or not isinstance(total, (int, float)) or count <= 0:
                continue
            course.difficulty_avg = total / count
            course.difficulty_count = count
            updated += 1
        session.commit()
        return updated
    finally:
        session.close()
