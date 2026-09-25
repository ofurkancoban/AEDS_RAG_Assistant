"""The limiter itself, with the multi-worker property it exists to provide."""

import threading
import time

from api.rate_limit import RateLimiter
from db.models import RateLimitEvent, SessionLocal


def test_events_are_allowed_up_to_the_limit_then_refused():
    limiter = RateLimiter("unit", [(3, 3600)])

    assert [limiter.check_and_record("alice") for _ in range(3)] == [True, True, True]
    assert limiter.check_and_record("alice") is False


def test_a_refused_request_does_not_consume_quota():
    limiter = RateLimiter("unit", [(1, 3600)])
    limiter.check_and_record("alice")

    for _ in range(5):
        assert limiter.check_and_record("alice") is False

    session = SessionLocal()
    try:
        # Five refusals must not leave five rows behind, or a blocked client
        # would extend its own lockout by retrying.
        assert session.query(RateLimitEvent).count() == 1
    finally:
        session.close()


def test_keys_are_independent():
    limiter = RateLimiter("unit", [(1, 3600)])
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("bob") is True
    assert limiter.check_and_record("alice") is False


def test_limiters_do_not_share_a_bucket_even_for_the_same_key():
    chat = RateLimiter("chat-unit", [(1, 3600)])
    submissions = RateLimiter("submission-unit", [(1, 3600)])

    assert chat.check_and_record("user:1") is True
    # Same client key, different limiter: spending one must not spend the other.
    assert submissions.check_and_record("user:1") is True


def test_two_workers_share_one_window():
    """The reason this state lives in the database at all.

    Two RateLimiter objects with the same name are what two uvicorn workers
    look like: separate instances, one shared store. Under the old in-memory
    implementation this test would allow four requests instead of two.
    """
    worker_a = RateLimiter("shared", [(2, 3600)])
    worker_b = RateLimiter("shared", [(2, 3600)])

    assert worker_a.check_and_record("alice") is True
    assert worker_b.check_and_record("alice") is True
    assert worker_a.check_and_record("alice") is False
    assert worker_b.check_and_record("alice") is False


def test_concurrent_checks_never_exceed_the_limit():
    """Two callers must not both read "one slot left" and both take it."""
    limiter = RateLimiter("racy", [(5, 3600)])
    results = []
    lock = threading.Lock()

    def hammer():
        allowed = limiter.check_and_record("alice")
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=hammer) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 5, f"granted {sum(results)} of a limit of 5"


def test_several_windows_apply_at_once():
    # A burst rule and a longer-horizon rule on one limiter.
    limiter = RateLimiter("unit", [(2, 1), (3, 3600)])

    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is True
    # Burst window full even though the hourly one is not.
    assert limiter.check_and_record("alice") is False

    time.sleep(1.1)
    assert limiter.check_and_record("alice") is True
    # Hourly window now full.
    assert limiter.check_and_record("alice") is False


def test_events_age_out_of_the_window():
    limiter = RateLimiter("unit", [(1, 1)])
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("alice") is False

    time.sleep(1.1)
    assert limiter.check_and_record("alice") is True


def test_expired_rows_are_pruned_rather_than_accumulating():
    limiter = RateLimiter("unit", [(10, 1)])
    for _ in range(3):
        limiter.check_and_record("alice")

    time.sleep(1.1)
    limiter.check_and_record("alice")

    session = SessionLocal()
    try:
        # Only the fresh event survives; without pruning this table would grow
        # for the lifetime of the deployment.
        assert session.query(RateLimitEvent).count() == 1
    finally:
        session.close()


def test_retry_after_reports_when_a_slot_frees_up():
    limiter = RateLimiter("unit", [(1, 60)])
    limiter.check_and_record("alice")

    wait = limiter.retry_after("alice")
    assert 0 < wait <= 60
    # A client under the limit is not told to wait at all.
    assert limiter.retry_after("bob") == 0


def test_reset_clears_one_key_or_the_whole_limiter():
    limiter = RateLimiter("unit", [(1, 3600)])
    limiter.check_and_record("alice")
    limiter.check_and_record("bob")

    limiter.reset("alice")
    assert limiter.check_and_record("alice") is True
    assert limiter.check_and_record("bob") is False

    limiter.reset()
    assert limiter.check_and_record("bob") is True
