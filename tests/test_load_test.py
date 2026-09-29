"""scripts/load_test.py's summarize(): the pure aggregation over a batch of
RequestResult - the part testable without a live server. The HTTP-issuing
parts (run, _obtain_guest_token) are exercised by hand against a running
instance, matching this project's convention for operational scripts (see
tests/test_export_review_cases.py's own note on this)."""

from scripts.load_test import RequestResult, summarize


def test_empty_batch_reports_zero_without_dividing_by_zero():
    summary = summarize([])
    assert summary == {"count": 0, "errors": 0, "error_rate": 0.0}


def test_all_successful_requests_have_no_errors():
    results = [RequestResult(latency_ms=10.0, status_code=200) for _ in range(5)]
    summary = summarize(results)
    assert summary["count"] == 5
    assert summary["errors"] == 0
    assert summary["error_rate"] == 0.0


def test_a_network_error_counts_as_a_failure_even_with_no_status_code():
    results = [
        RequestResult(latency_ms=5.0, status_code=200),
        RequestResult(latency_ms=1.0, status_code=None, error="Connection refused"),
    ]
    summary = summarize(results)
    assert summary["errors"] == 1
    assert summary["error_rate"] == 0.5


def test_a_5xx_status_counts_as_a_failure():
    results = [RequestResult(latency_ms=1.0, status_code=200), RequestResult(latency_ms=1.0, status_code=503)]
    summary = summarize(results)
    assert summary["errors"] == 1


def test_a_4xx_status_counts_as_a_failure():
    # A rate limiter returning 429 is exactly the kind of thing a load test
    # should surface as a failure, not silently average into "ok".
    results = [RequestResult(latency_ms=1.0, status_code=200), RequestResult(latency_ms=1.0, status_code=429)]
    summary = summarize(results)
    assert summary["errors"] == 1


def test_latency_percentiles_are_computed_from_sorted_latencies():
    results = [RequestResult(latency_ms=ms, status_code=200) for ms in [10, 20, 30, 40, 100]]
    summary = summarize(results)
    assert summary["min_ms"] == 10.0
    assert summary["max_ms"] == 100.0
    assert summary["median_ms"] == 30.0
