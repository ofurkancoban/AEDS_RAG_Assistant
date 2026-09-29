"""Concurrent HTTP load test against a running instance of this API.

Why this exists. Nothing in this project had ever measured what happens
under concurrent load - not the reverse proxy, not the rate limiter, not
the answer pipeline itself. The per-client rate limiter (api/rate_limit.py)
and the per-provider daily budget (llm_budget.py) were both sized from
written-down reasoning about expected usage, never from an actual
measurement of latency or error rate under load.

Safety. Defaults to GET /health: cheap, no auth, no side effects, not rate
limited. --chat instead hits POST /chat with a real question, which spends
real LLM budget (llm_budget.py) and counts against the real per-client rate
limiter exactly like a real user would - so it is opt-in, and --requests
should stay small (a handful, not hundreds) against a shared production
target. Never hit a production URL's --chat with high concurrency/request
counts without deciding that is actually intended: it competes with real
students for the same daily budget and rate-limit windows this project
protects specifically because they are scarce.

Usage:
    PYTHONPATH=. python scripts/load_test.py --url http://localhost:8000
    PYTHONPATH=. python scripts/load_test.py --url http://localhost:8000 \
        --concurrency 20 --requests 200
    PYTHONPATH=. python scripts/load_test.py --url http://localhost:8000 \
        --chat --requests 5 --concurrency 1   # spends real LLM quota
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests


@dataclass
class RequestResult:
    latency_ms: float
    status_code: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 400


def _one_request(session: requests.Session, method: str, url: str, timeout: float, **kwargs) -> RequestResult:
    start = time.monotonic()
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
        return RequestResult(latency_ms=(time.monotonic() - start) * 1000, status_code=response.status_code)
    except requests.RequestException as exc:
        return RequestResult(latency_ms=(time.monotonic() - start) * 1000, status_code=None, error=str(exc))


def summarize(results: list[RequestResult]) -> dict:
    """Pure aggregation - no network, so this is the part covered by
    tests/test_load_test.py without needing a live server."""
    if not results:
        return {"count": 0, "errors": 0, "error_rate": 0.0}

    latencies = sorted(r.latency_ms for r in results)
    errors = [r for r in results if not r.ok]

    def _percentile(p: float) -> float:
        index = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[index]

    return {
        "count": len(results),
        "errors": len(errors),
        "error_rate": round(len(errors) / len(results), 3),
        "min_ms": round(latencies[0], 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "median_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(_percentile(0.95), 1),
        "p99_ms": round(_percentile(0.99), 1),
        "max_ms": round(latencies[-1], 1),
    }


def run(url: str, method: str, concurrency: int, total_requests: int, timeout: float, **request_kwargs) -> list[RequestResult]:
    results: list[RequestResult] = []
    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(_one_request, session, method, url, timeout, **request_kwargs)
                for _ in range(total_requests)
            ]
            for future in as_completed(futures):
                results.append(future.result())
    return results


def _obtain_guest_token(base_url: str, timeout: float) -> str:
    response = requests.post(f"{base_url}/auth/guest", timeout=timeout)
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of a running instance")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=100, dest="total_requests")
    parser.add_argument("--endpoint", default="/health", help="Path to hit GET on, ignored if --chat is set")
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Hit POST /chat with a real question instead of --endpoint - spends real LLM "
        "budget and real rate-limit quota, see this script's own docstring before using "
        "this against a production URL",
    )
    parser.add_argument("--question", default="What is the AEDS programme?")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.05,
        help="Exit 1 if the observed error rate exceeds this fraction (default 0.05)",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    if args.chat:
        print("Obtaining a guest token...")
        token = _obtain_guest_token(base_url, args.timeout)
        results = run(
            f"{base_url}/chat",
            "POST",
            args.concurrency,
            args.total_requests,
            args.timeout,
            json={"message": args.question},
            headers={"Authorization": f"Bearer {token}"},
        )
    else:
        results = run(f"{base_url}{args.endpoint}", "GET", args.concurrency, args.total_requests, args.timeout)

    summary = summarize(results)
    print(f"\n{args.total_requests} requests, concurrency {args.concurrency}, target {base_url}")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    if summary["error_rate"] > args.max_error_rate:
        print(f"\nFAILED: error rate {summary['error_rate']} exceeds --max-error-rate {args.max_error_rate}")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
