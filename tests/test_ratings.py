"""ingestion/ratings.py syncs AEDS_ECTS_Tracker's own anonymous
difficulty-rating data (ratings.json, code -> {count, sum}) onto the Course
table here, so the schedule recommender (graph/nodes.py) can prefer easier
electives when there's a genuine choice. These tests cover the sync logic
in isolation, using throwaway "ratingtest_*" course codes so they never
collide with real catalog rows seeded by other tests in the shared session
database."""

from __future__ import annotations

import pytest

from db.models import Course, SessionLocal
from ingestion.ratings import sync_ratings_to_sql


@pytest.fixture
def seeded_courses():
    """Two Course rows this file owns end to end - inserted here, deleted in
    the fixture's teardown regardless of what the test did to them."""
    session = SessionLocal()
    try:
        session.add_all(
            [
                Course(code="ratingtest_easy", name="Easy Test Course", category="specialization", ects=6),
                Course(code="ratingtest_hard", name="Hard Test Course", category="specialization", ects=6),
            ]
        )
        session.commit()
    finally:
        session.close()

    yield ["ratingtest_easy", "ratingtest_hard"]

    session = SessionLocal()
    try:
        session.query(Course).filter(Course.code.in_(["ratingtest_easy", "ratingtest_hard"])).delete(
            synchronize_session=False
        )
        session.commit()
    finally:
        session.close()


def _get(code: str) -> Course:
    session = SessionLocal()
    try:
        return session.query(Course).filter(Course.code == code).one()
    finally:
        session.close()


class TestSyncRatingsToSql:
    def test_updates_matching_courses_with_the_average_and_count(self, seeded_courses):
        updated = sync_ratings_to_sql(
            {"ratingtest_easy": {"count": 4, "sum": 8}, "ratingtest_hard": {"count": 2, "sum": 10}}
        )
        assert updated == 2
        easy = _get("ratingtest_easy")
        assert easy.difficulty_avg == pytest.approx(2.0)
        assert easy.difficulty_count == 4
        hard = _get("ratingtest_hard")
        assert hard.difficulty_avg == pytest.approx(5.0)
        assert hard.difficulty_count == 2

    def test_code_not_in_the_catalog_is_ignored_not_inserted(self, seeded_courses):
        updated = sync_ratings_to_sql({"not_a_real_course": {"count": 3, "sum": 9}})
        assert updated == 0
        session = SessionLocal()
        try:
            assert session.query(Course).filter(Course.code == "not_a_real_course").first() is None
        finally:
            session.close()

    def test_code_matching_is_case_insensitive(self, seeded_courses):
        updated = sync_ratings_to_sql({"RATINGTEST_EASY": {"count": 1, "sum": 3}})
        assert updated == 1
        assert _get("ratingtest_easy").difficulty_avg == pytest.approx(3.0)

    def test_malformed_entries_are_skipped(self, seeded_courses):
        updated = sync_ratings_to_sql(
            {
                "ratingtest_easy": {"count": 0, "sum": 0},  # zero votes - nothing to average
                "ratingtest_hard": {"count": "three", "sum": 10},  # wrong type
            }
        )
        assert updated == 0
        assert _get("ratingtest_easy").difficulty_avg is None
        assert _get("ratingtest_hard").difficulty_avg is None

    def test_a_partial_or_failed_fetch_does_not_wipe_existing_ratings(self, seeded_courses):
        sync_ratings_to_sql({"ratingtest_easy": {"count": 4, "sum": 8}})
        assert _get("ratingtest_easy").difficulty_avg == pytest.approx(2.0)
        # Second sync only mentions a course this file doesn't even seed -
        # ratingtest_easy's real number from the first sync must survive,
        # unlike sync_catalog_to_sql's delete-everything-then-reinsert.
        sync_ratings_to_sql({"some_other_course": {"count": 1, "sum": 1}})
        assert _get("ratingtest_easy").difficulty_avg == pytest.approx(2.0)


class TestFetchRatings:
    def test_parses_a_well_formed_response(self, monkeypatch):
        import io
        import ingestion.ratings as ratings_module

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        payload = b'{"wir821": {"count": 3, "sum": 7}}'
        monkeypatch.setattr(
            ratings_module.urllib.request, "urlopen", lambda req, timeout=30: FakeResponse(payload)
        )
        result = ratings_module.fetch_ratings()
        assert result == {"wir821": {"count": 3, "sum": 7}}

    def test_rejects_a_non_object_response(self, monkeypatch):
        import io
        import ingestion.ratings as ratings_module

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(
            ratings_module.urllib.request, "urlopen", lambda req, timeout=30: FakeResponse(b"[1, 2, 3]")
        )
        with pytest.raises(ValueError):
            ratings_module.fetch_ratings()
