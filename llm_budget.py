"""Global daily ceiling on LLM requests.

The per-client rate limiter (api/rate_limit.py) stops one visitor from
monopolising the quota, but it cannot bound TOTAL consumption - twenty
different clients staying individually within their limits can still exhaust
the provider's daily allowance between them. This module is that global
control.

Counting happens at the point requests are actually issued (a LangChain
callback on the chat model, see graph/nodes.py), not per chat turn, because
the number of calls per turn varies: the tool router always runs, generation
runs unless a tool answered directly, the contribution classifier runs only
for messages that look like assertions, and _with_resilience retries on rate
limits - every one of which spends real quota.

When the budget is gone the assistant refuses new pipeline runs but continues
serving cached answers, so it degrades to a smaller, still-useful service
rather than going dark.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from config import settings
from db.models import DailyLlmUsage, SessionLocal

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_call() -> None:
    """Count one issued LLM request. Never raises: a bookkeeping failure must
    not take down the answer the user is waiting for."""
    day = _today()
    session = SessionLocal()
    try:
        # UPDATE-then-INSERT rather than read-modify-write, so concurrent
        # requests increment atomically in SQLite instead of overwriting each
        # other's count.
        updated = session.execute(
            update(DailyLlmUsage)
            .where(DailyLlmUsage.day == day)
            .values(call_count=DailyLlmUsage.call_count + 1)
        ).rowcount
        if not updated:
            session.add(DailyLlmUsage(day=day, call_count=1))
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("Failed to record LLM call against the daily budget", exc_info=True)
    finally:
        session.close()


def usage_today() -> int:
    session = SessionLocal()
    try:
        row = session.get(DailyLlmUsage, _today())
        return row.call_count if row else 0
    finally:
        session.close()


def remaining() -> int:
    return max(0, settings.effective_daily_llm_budget - usage_today())


def has_headroom(estimated_calls: int = 3) -> bool:
    """Whether a turn about to start can be afforded.

    estimated_calls defaults to the worst case for one turn (router +
    generation + contribution classifier) so the budget is checked against
    what the turn might cost rather than the single call that would trip it
    mid-answer, which would leave the user with a half-finished response.
    """
    if settings.effective_daily_llm_budget <= 0:
        # No ceiling configured - the usual case for a local model, which has
        # no external quota to protect.
        return True
    return remaining() >= estimated_calls
