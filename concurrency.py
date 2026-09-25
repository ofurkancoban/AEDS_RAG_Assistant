"""Thread-safe lazy singletons for expensive, shared resources.

functools.lru_cache does not hold a lock while the wrapped function runs, so
concurrent first-callers all miss the cache and all execute the body. For a
cheap function that is merely wasteful; for the ones this module guards it was
fatal - five simultaneous chat requests each began loading their own copy of
the 1.3 GB embedding model and the server process was killed mid-request, with
every one of those users getting a dropped connection.

FastAPI runs sync endpoints in a thread pool, so "concurrent" here is the
normal case as soon as more than one person uses the assistant at the same
time - it is not an edge case that needs unusual load to reach.
"""

import functools
import threading

_MISSING = object()


def once(fn):
    """Run fn at most once, however many threads race to it.

    The first caller builds the value while later callers block on the lock and
    then share the result, instead of each building their own. Only for
    zero-argument factories - the whole point is that there is exactly one
    instance to share.

    Exposes cache_clear() so it is a drop-in for the lru_cache(maxsize=1) uses
    it replaces, including the ones that reset state in tests.
    """
    lock = threading.Lock()
    cell = {"value": _MISSING}

    @functools.wraps(fn)
    def wrapper():
        # Fast path: no lock once the value exists, so the common case costs a
        # dict read rather than lock acquisition on every retrieval.
        value = cell["value"]
        if value is not _MISSING:
            return value

        with lock:
            # Re-checked inside the lock: another thread may have finished
            # building while this one was waiting for it.
            if cell["value"] is _MISSING:
                cell["value"] = fn()
            return cell["value"]

    def cache_clear() -> None:
        with lock:
            cell["value"] = _MISSING

    wrapper.cache_clear = cache_clear
    return wrapper
