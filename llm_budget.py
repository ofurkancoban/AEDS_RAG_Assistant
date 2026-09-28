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


def _live_daily_budget() -> int:
    """Like settings.effective_daily_llm_budget, but against the admin-
    switchable runtime provider (see runtime_config.py) rather than the one
    fixed in .env at process start - otherwise switching the provider live
    left this ceiling stuck at whichever provider's number was baked in at
    startup, which is actively dangerous for a tight quota (an admin
    switching to openrouter mid-run would keep gemini's 450/day ceiling
    instead of openrouter's real 45, with no protection until it started
    failing with raw 429s)."""
    from config import daily_budget_for_provider, settings
    from runtime_config import get_runtime_config

    return daily_budget_for_provider(get_runtime_config().llm_provider, settings.daily_llm_call_budget)


def daily_budget() -> int:
    """Public wrapper on _live_daily_budget, for callers outside this module
    (the Telegram /budget command) that need the raw ceiling itself - 0 means
    unlimited, which remaining() alone cannot distinguish from "no budget
    left" since it also reports 0 in that case."""
    return _live_daily_budget()


def remaining() -> int:
    return max(0, _live_daily_budget() - usage_today())


def has_headroom(estimated_calls: int = 3) -> bool:
    """Whether a turn about to start can be afforded.

    estimated_calls defaults to the worst case for one turn (router +
    generation + contribution classifier) so the budget is checked against
    what the turn might cost rather than the single call that would trip it
    mid-answer, which would leave the user with a half-finished response.
    """
    if _live_daily_budget() <= 0:
        # No ceiling configured - the usual case for a local model, which has
        # no external quota to protect.
        return True
    return remaining() >= estimated_calls
