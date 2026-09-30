"""db/models.py's migration for the cross-process race llm_budget.py's
dedup couldn't fully close on its own (see its docstring): two processes
can both pass the "is today already recorded" check before either commits,
so the real guarantee is a unique index on BudgetFallbackEvent.day, with
_dedupe_budget_fallback_events cleaning up any duplicates a pre-fix
production database already accumulated before that index can be created
(SQLite refuses a unique index over data that already violates it)."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.models import BudgetFallbackEvent, SessionLocal, _add_missing_indexes, _dedupe_budget_fallback_events, engine


def _insert_raw(day: str, usage: int, created_at: str) -> None:
    """Bypasses the ORM/unique-index path - simulates a row already on disk
    from before this migration existed, the same way the real production
    database ended up with duplicates.

    conftest.py's app-startup fixture already calls init_db() once per test
    session, so by the time any test here runs, the unique index this
    module tests already exists - dropped first so a raw insert can still
    put two rows on the same day, the state _dedupe_budget_fallback_events
    is meant to clean up."""
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_budget_fallback_events_day_unique"))
        conn.execute(
            text(
                "INSERT INTO budget_fallback_events "
                "(day, from_provider, to_provider, usage_at_switch, created_at) "
                "VALUES (:day, 'openrouter', 'gemini', :usage, :created_at)"
            ),
            {"day": day, "usage": usage, "created_at": created_at},
        )


def test_dedupe_keeps_only_the_earliest_row_per_day():
    _insert_raw("2026-09-29", 63, "2026-09-29 13:33:00")
    _insert_raw("2026-09-29", 67, "2026-09-29 13:41:00")
    _insert_raw("2026-09-28", 45, "2026-09-28 10:00:00")

    _dedupe_budget_fallback_events()

    session = SessionLocal()
    try:
        rows = {r.day: r.usage_at_switch for r in session.query(BudgetFallbackEvent).all()}
    finally:
        session.close()

    assert rows == {"2026-09-29": 63, "2026-09-28": 45}


def test_add_missing_indexes_succeeds_even_right_after_a_dedupe():
    _insert_raw("2026-09-29", 63, "2026-09-29 13:33:00")
    _insert_raw("2026-09-29", 67, "2026-09-29 13:41:00")

    _dedupe_budget_fallback_events()
    _add_missing_indexes()  # must not raise


def test_the_unique_index_rejects_a_new_duplicate_after_migration():
    _insert_raw("2026-09-29", 63, "2026-09-29 13:33:00")
    _dedupe_budget_fallback_events()
    _add_missing_indexes()

    session = SessionLocal()
    try:
        session.add(
            BudgetFallbackEvent(day="2026-09-29", from_provider="openrouter", to_provider="gemini", usage_at_switch=99)
        )
        try:
            session.commit()
            assert False, "duplicate day should have been rejected by the unique index"
        except IntegrityError:
            session.rollback()
    finally:
        session.close()


def test_add_missing_indexes_is_idempotent_on_an_already_migrated_database():
    _add_missing_indexes()
    _add_missing_indexes()  # must not raise the second time either
