"""Sliding-window rate limiting, shared across processes.

Every visitor now holds their own identity (see api/auth.py's
create_guest_user), so limits are keyed per identity rather than per IP, with
an IP limiter underneath as a backstop against identity farming.

Counters live in SQLite rather than in each process, because a limit that
multiplies by the number of uvicorn workers is not a limit anyone can reason
about. See RateLimiter.

The limiters guard different scarce resources:

  submission_limiter - protects the admin review queue from being spammed
                       with garbage entries.
  auth_limiter       - bounds password guessing against accounts the caller
                       does not own.
  guest_limiter      - bounds how fast new identities can be minted, since
                       each one inserts a users row.
  get_chat_limiter() - protects the answer pipeline, picking the rule set for
                       the live LLM provider (runtime_config.py) - against a
                       metered API that is a daily quota one visitor could
                       otherwise drain for everyone; against the local model
                       it is CPU time. A function, not a constant, because
                       the provider is admin-switchable without a restart.

A per-client limit cannot cap total consumption across many clients; it stops
one actor from monopolising it. Capping total daily spend is a separate,
global control (see llm_budget.py).
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import Request

from config import settings

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def client_ip(request: Request) -> str:
    """The caller's address, used as the key for every limiter here.

    This deliberately does NOT parse X-Forwarded-For. Uvicorn already does it:
    ProxyHeadersMiddleware is enabled by default and rewrites the client
    address by walking the XFF chain from the right, so request.client.host is
    the real client whenever the request arrived through a trusted proxy.
    Re-deriving it here would apply the hop logic twice.

    What this DOES depend on is uvicorn's --forwarded-allow-ips, which decides
    whose XFF is believed:

      * default "127.0.0.1" - correct for the usual VPS layout (nginx/Caddy on
        the same host proxying to uvicorn on loopback). Every user then gets
        their own limiter bucket.
      * "*" - trusts the header from ANY caller. Widely copied from Docker
        guides and unsafe here: a client can then forge an address per request
        and bypass every limit in this module.

    Get it wrong in the other direction (proxy present, uvicorn not told to
    trust it) and every request looks like it came from the proxy, collapsing
    all users into one bucket - 20 questions/hour for the whole cohort, and
    only 5 new visitors per hour able to obtain a session at all.
    """
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limiter supporting several windows at once, so one
    limiter can express both a burst rule and a longer-horizon rule (e.g. 20
    per hour AND 60 per day) instead of stacking two objects.

    State lives in SQLite (db.models.RateLimitEvent), not in this object. The
    limits describe what one person may do, and a process-local deque cannot
    express that once more than one worker is running: each worker would keep
    its own count, so the effective allowance became the configured number
    times the worker count, varying with which worker took each request. That
    made "how many questions may a student ask" unanswerable from the config
    alone, and it silently loosened every limit the moment the deployment
    scaled past one process.

    The cost is one small write transaction per allowed request. At these
    volumes (hundreds per hour across everyone) that is far below the cost of
    the embedding call the same request goes on to make.
    """

    def __init__(self, name: str, rules: list[tuple[int, int]]):
        # name namespaces the rows, so two limiters never share a bucket even
        # when they are keyed by the same client identifier.
        self.name = name
        # rules: (max_events, window_seconds), kept sorted by window length so
        # the longest window drives pruning.
        self._rules = sorted(rules, key=lambda rule: rule[1])

    def _bucket(self, key: str) -> str:
        return f"{self.name}:{key}"

    @property
    def _longest_window(self) -> int:
        return self._rules[-1][1]

    def check_and_record(self, key: str) -> bool:
        """Returns True (recording the event) if key is under every rule,
        False if any window is already full.

        The whole check runs inside one immediate (write-lock-holding)
        transaction, so two workers cannot both read "one slot left" and both
        take it.
        """
        from db.models import engine

        bucket = self._bucket(key)
        now = time.time()
        cutoff = now - self._longest_window

        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                connection.exec_driver_sql(
                    "DELETE FROM rate_limit_events WHERE bucket = ? AND created_at < ?",
                    (bucket, cutoff),
                )
                timestamps = self._timestamps(connection, bucket, cutoff)

                for max_events, window in self._rules:
                    if sum(1 for t in timestamps if now - t <= window) >= max_events:
                        # A rejected request does not consume quota, matching
                        # the behaviour callers already relied on - but it is
                        # still worth counting on its own, so this limiter's
                        # tightness is visible somewhere (see
                        # RateLimitRejectionDaily) instead of only inferable
                        # from support complaints.
                        connection.exec_driver_sql("COMMIT")
                        self._record_rejection()
                        return False

                connection.exec_driver_sql(
                    "INSERT INTO rate_limit_events (bucket, created_at) VALUES (?, ?)",
                    (bucket, now),
                )
                connection.exec_driver_sql("COMMIT")
                return True
            except Exception:
                connection.exec_driver_sql("ROLLBACK")
                raise

    def retry_after(self, key: str) -> int:
        """Seconds until the tightest exceeded window frees a slot, so a 429
        can carry a Retry-After the caller can actually act on."""
        from db.models import engine

        bucket = self._bucket(key)
        now = time.time()
        cutoff = now - self._longest_window

        with engine.connect() as connection:
            timestamps = self._timestamps(connection, bucket, cutoff)

        waits = []
        for max_events, window in self._rules:
            in_window = [t for t in timestamps if now - t <= window]
            if len(in_window) >= max_events:
                # the oldest event still inside this window has to age out
                # before another one is allowed
                waits.append(window - (now - in_window[0]))
        return max(1, int(max(waits))) if waits else 0

    def _record_rejection(self) -> None:
        """Best-effort daily tally of this limiter's rejections. Never
        raises: a bookkeeping failure here must not turn an otherwise-correct
        429 into a 500."""
        from sqlalchemy import update

        from db.models import RateLimitRejectionDaily, SessionLocal

        day = _today()
        session = SessionLocal()
        try:
            updated = session.execute(
                update(RateLimitRejectionDaily)
                .where(
                    RateLimitRejectionDaily.day == day,
                    RateLimitRejectionDaily.limiter_name == self.name,
                )
                .values(count=RateLimitRejectionDaily.count + 1)
            ).rowcount
            if not updated:
                session.add(RateLimitRejectionDaily(day=day, limiter_name=self.name, count=1))
            session.commit()
        except Exception:
            session.rollback()
            logger.warning("Failed to record a rate-limit rejection for %s", self.name, exc_info=True)
        finally:
            session.close()

    @staticmethod
    def _timestamps(connection, bucket: str, cutoff: float) -> list[float]:
        rows = connection.exec_driver_sql(
            "SELECT created_at FROM rate_limit_events "
            "WHERE bucket = ? AND created_at >= ? ORDER BY created_at",
            (bucket, cutoff),
        ).fetchall()
        return [row[0] for row in rows]

    def reset(self, key: str | None = None) -> None:
        """Forget recorded events, for one key or for this limiter entirely.

        Used by the test suite between cases, and available to an operator who
        has to lift a limit for someone without waiting out the window.
        """
        from db.models import engine

        with engine.begin() as connection:
            if key is None:
                connection.exec_driver_sql(
                    "DELETE FROM rate_limit_events WHERE bucket LIKE ?", (f"{self.name}:%",)
                )
            else:
                connection.exec_driver_sql(
                    "DELETE FROM rate_limit_events WHERE bucket = ?", (self._bucket(key),)
                )


submission_limiter = RateLimiter("submission", [(5, 3600)])

# Sized to the provider, because what is scarce differs completely between
# them. Against Gemini a turn spends 2-3 requests from a ~500/day free-tier
# quota, so one heavy user really can take the assistant down for everyone.
# Against openrouter's free tier that quota is far tighter still (50/day
# total with no purchased credits - see config.py's openrouter_api_key
# field), so one user left unchecked could burn the whole day's budget alone
# in under an hour even at these numbers; llm_budget.py's GLOBAL daily
# ceiling is what actually protects that, this is just the per-person share
# of it. A local model has no such quota - the only cost is CPU time, which
# the hardware already bounds at roughly 8 questions a minute for the whole
# server.
#
# The tight Gemini numbers were being applied to the local default too, which
# made a normal session hit "too many questions" for no saving at all: the
# sidebar alone offers 15 one-click queries, so simply exploring the
# suggestions consumed most of a 20/hour allowance in a couple of minutes.
_CHAT_RULES = {
    "gemini": [(20, 3600), (60, 86400)],
    "openrouter": [(10, 3600), (30, 86400)],
    "ollama": [(30, 3600), (150, 86400)],
}

# Credential endpoints (/auth/login, /auth/register). Keyed by source IP, since
# the whole point is to bound guessing against accounts the caller does not
# own. Both windows matter: the short one stops a fast burst, the long one
# stops a patient trickle.
auth_limiter = RateLimiter("auth", [(10, 300), (50, 3600)])

# /auth/guest inserts a users row per call, so it is capped by IP - but
# generously, because on a shared network (campus wifi, a lecture hall) every
# student arrives from the same address and each of them legitimately needs one
# identity. A row is ~100 bytes, so the cost of being generous here is
# negligible; what this really guards is identity farming, which the
# per-identity chat limit below then bounds again.
#
# Sized against the actual cohort: about 50 students, who may well open the
# assistant together at the start of one lecture, all from the same campus
# address. At the previous 30/hour the thirty-first person to open it that
# morning could not obtain a session at all - not throttled mid-use, but shut
# out before asking anything. The daily figure allows the same cohort to
# arrive several times over, e.g. from a lab and again from a lecture hall.
guest_limiter = RateLimiter("guest", [(60, 3600), (300, 86400)])

# Backstop, per IP, across every identity coming from that address. Keying
# chat per identity is right for fairness but forgeable on its own: a script
# can mint identities (within guest_limiter) and cycle them. This bounds that
# to roughly what the hardware can serve anyway - measured at ~8 questions a
# minute for the whole server on the local model - so an abuser cannot starve
# everyone else, while a busy shared network still fits underneath it.
_CHAT_IP_RULES = {
    "gemini": [(60, 3600), (200, 86400)],
    "openrouter": [(15, 3600), (40, 86400)],
    "ollama": [(300, 3600), (1200, 86400)],
}

# One RateLimiter per provider, built once - all sharing the same `name`
# ("chat" / "chat_ip"), so they read and write the SAME SQLite bucket
# regardless of which provider's numbers are currently in force (see
# RateLimiter._bucket: the bucket key is name+identity, never the rule
# list). A live provider switch (runtime_config.py) therefore just changes
# which thresholds apply to the same ongoing event history, rather than
# resetting anyone's count.
_chat_limiters = {provider: RateLimiter("chat", rules) for provider, rules in _CHAT_RULES.items()}
_chat_ip_limiters = {provider: RateLimiter("chat_ip", rules) for provider, rules in _CHAT_IP_RULES.items()}


def get_chat_limiter() -> RateLimiter:
    """Per person. Guests are keyed by their own identity rather than by IP,
    so students behind one campus address get an allowance each instead of
    sharing a single bucket between them - which, at the old numbers, worked
    out to about two questions each. Picks the instance for the LIVE
    provider (runtime_config.py), not the one fixed in .env at startup."""
    from runtime_config import get_runtime_config

    return _chat_limiters.get(get_runtime_config().llm_provider, _chat_limiters["gemini"])


def get_chat_ip_limiter() -> RateLimiter:
    from runtime_config import get_runtime_config

    return _chat_ip_limiters.get(get_runtime_config().llm_provider, _chat_ip_limiters["gemini"])


def check_and_record(key: str) -> bool:
    """Backwards-compatible entry point for the submission limiter."""
    return submission_limiter.check_and_record(key)
