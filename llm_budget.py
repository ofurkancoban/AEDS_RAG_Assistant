"""Per-provider daily ceiling on LLM requests.

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

Usage is tracked per (day, provider) - see db/models.py's
ProviderDailyUsage - not as one shared count across whatever providers
happened to be used. That distinction matters because of the daily-budget
fallback below: if openrouter and gemini shared one counter, "gemini has
room" could not be told apart from "openrouter's real quota is gone but
gemini has barely been touched today", and a fallback would inherit a
budget that was never really its own.

When neither the live provider nor its configured fallback has room left,
the assistant refuses new pipeline runs but continues serving cached
answers, so it degrades to a smaller, still-useful service rather than
going dark.
"""

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from db.models import BudgetFallbackEvent, ProviderDailyUsage, SessionLocal

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_call(provider: str) -> None:
    """Count one issued LLM request against `provider`. Never raises: a
    bookkeeping failure must not take down the answer the user is waiting
    for."""
    day = _today()
    session = SessionLocal()
    try:
        # UPDATE-then-INSERT rather than read-modify-write, so concurrent
        # requests increment atomically in SQLite instead of overwriting each
        # other's count.
        updated = session.execute(
            update(ProviderDailyUsage)
            .where(ProviderDailyUsage.day == day, ProviderDailyUsage.provider == provider)
            .values(call_count=ProviderDailyUsage.call_count + 1)
        ).rowcount
        if not updated:
            session.add(ProviderDailyUsage(day=day, provider=provider, call_count=1))
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("Failed to record an LLM call against %s's daily budget", provider, exc_info=True)
    finally:
        session.close()


def _live_provider() -> str:
    from runtime_config import get_runtime_config

    return get_runtime_config().llm_provider


def usage_today(provider: str | None = None) -> int:
    """Calls recorded today for `provider` - the live configured provider if
    not given."""
    if provider is None:
        provider = _live_provider()
    session = SessionLocal()
    try:
        row = session.get(ProviderDailyUsage, (_today(), provider))
        return row.call_count if row else 0
    finally:
        session.close()


def daily_budget(provider: str | None = None) -> int:
    """The raw daily ceiling for `provider` (the live configured provider if
    not given) - 0 means unlimited, which remaining() alone cannot
    distinguish from "no budget left" since it also reports 0 in that
    case."""
    from config import daily_budget_for_provider, settings

    if provider is None:
        provider = _live_provider()
    return daily_budget_for_provider(provider, settings.daily_llm_call_budget)


def remaining(provider: str | None = None) -> int:
    if provider is None:
        provider = _live_provider()
    return max(0, daily_budget(provider) - usage_today(provider))


_notified_fallback_day: str | None = None
_notified_fallback_lock = threading.Lock()


def _record_fallback_engaged(live: str, fallback: str, reason: str | None = None) -> None:
    """Best-effort, once per calendar day: writes a BudgetFallbackEvent row
    (see db/models.py - the persistent record recent_fallback_events reads
    back for the admin panel) and sends the matching Telegram alert. A
    budget fallback changes which provider is actually answering without
    the admin panel's live-provider display changing to say so on its own,
    so this is the only place that surfaces it - the same reasoning as
    graph/nodes.py's model-level fallback getting its own alert.

    Deduped against the BudgetFallbackEvent table itself, not just an
    in-process flag: the flag alone (this module's previous approach)
    reset to unset on every fresh process - a pm2 restart, a cron script,
    or a one-off debugging script that imports this module - so any of
    those importing "today's budget is already exhausted" state sent its
    own duplicate alert, independent of whatever the long-running API
    process had already sent. Checking the table instead makes today's
    event count shared truth across every process. The module-level
    _notified_fallback_day flag stays as a same-process fast path (skips a
    DB round trip on the common case, a call after this process has
    already recorded today's row), guarded by a lock so two threads in
    the same process racing the check-then-set can't both fall through
    (the concurrency.py module documents exactly this class of bug for
    FastAPI's thread-pooled sync endpoints)."""
    global _notified_fallback_day
    today = _today()
    if _notified_fallback_day == today:
        return

    with _notified_fallback_lock:
        if _notified_fallback_day == today:
            return

        session = SessionLocal()
        try:
            already_recorded = (
                session.query(BudgetFallbackEvent.id).filter(BudgetFallbackEvent.day == today).first()
                is not None
            )
            if already_recorded:
                _notified_fallback_day = today
                return

            used = usage_today(live)
            lost_the_race = False
            try:
                session.add(
                    BudgetFallbackEvent(day=today, from_provider=live, to_provider=fallback, usage_at_switch=used)
                )
                session.commit()
            except IntegrityError:
                # Another process (see the docstring above: a pm2 restart, a
                # cron script, a one-off diagnostic script - all racing
                # against the same day's already-empty table) committed its
                # own row for `today` between this function's SELECT check
                # and this INSERT - the unique index on `day`
                # (db/models.py's _add_missing_indexes) is what turns that
                # into this exception instead of a silent second row. That
                # other process already sent the alert, so this one must not
                # send a duplicate.
                session.rollback()
                lost_the_race = True
            except Exception:
                session.rollback()
                logger.warning("Failed to record budget-fallback event", exc_info=True)
        finally:
            session.close()

        _notified_fallback_day = today
        if lost_the_race:
            return

        try:
            from api.telegram_bot import _notify_admins

            _notify_admins(
                f"{reason} - falling back to {fallback} until 00:00 UTC."
                if reason
                else f"{live}'s daily budget is exhausted ({used} calls today) - "
                f"falling back to {fallback} for the rest of the day."
            )
        except Exception:
            logger.warning("Failed to send budget-fallback Telegram alert", exc_info=True)


def recent_fallback_events(limit: int = 20) -> list[dict]:
    """Most recent budget-fallback switches, newest first - what the admin
    panel's history list reads. Each row is one calendar day's first (and
    only recorded) engagement, not one per request."""
    session = SessionLocal()
    try:
        rows = (
            session.query(BudgetFallbackEvent)
            .order_by(BudgetFallbackEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "day": row.day,
                "from_provider": row.from_provider,
                "to_provider": row.to_provider,
                "usage_at_switch": row.usage_at_switch,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    finally:
        session.close()


def effective_provider() -> str:
    """Which provider actually answers the next call: the live configured
    one (runtime_config.llm_provider), unless ITS OWN daily budget is
    exhausted and RuntimeConfig.daily_budget_fallback_provider names a
    different provider that still has headroom of ITS OWN - in which case
    that fallback takes over for the rest of the day, rather than refusing
    every new question outright the moment the primary's ceiling is hit.

    Each provider's usage is tracked independently (see module docstring),
    so this is an exact check, not an approximation - a fallback's headroom
    is really its own, unaffected by how much quota some other provider has
    burned today.

    graph/nodes.py's get_llm()/get_classifier_llm(), _with_fallback, and
    _with_resilience all call this rather than reading
    get_runtime_config().llm_provider directly, so a budget-triggered
    switch to gemini this call also correctly skips openrouter's own
    model-level fallback and retry policy for that same call.
    """
    live = _live_provider()

    if daily_budget(live) <= 0 or usage_today(live) < daily_budget(live):
        return live

    from runtime_config import get_runtime_config

    fallback = get_runtime_config().daily_budget_fallback_provider
    if fallback and fallback != live:
        if daily_budget(fallback) <= 0 or usage_today(fallback) < daily_budget(fallback):
            _record_fallback_engaged(live, fallback)
            return fallback

    return live


def mark_exhausted(provider: str, detail: str = "") -> bool:
    """The provider itself refused with "daily quota exhausted". Fills
    today's counter up to the budget, so effective_provider() moves every
    process to the fallback until the next UTC day - which is when
    OpenRouter's free-model quota resets. Needed because the counter only
    sees this server's calls: on 2026-10-10 the account quota was used up
    from elsewhere (local evaluation runs) while this counter stood at 26,
    so nothing switched and every question retried a 429 for minutes.

    Returns True when a fallback provider now serves the next call."""
    budget = daily_budget(provider)
    if budget <= 0:
        logger.warning("%s reported its daily quota exhausted, but it has no budget to fill", provider)
        return False

    used_before = usage_today(provider)
    day = _today()
    session = SessionLocal()
    try:
        row = session.get(ProviderDailyUsage, (day, provider))
        if row is None:
            session.add(ProviderDailyUsage(day=day, provider=provider, call_count=budget))
        else:
            row.call_count = max(row.call_count, budget)
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("Failed to mark %s's daily quota as exhausted", provider, exc_info=True)
        return False
    finally:
        session.close()

    from runtime_config import get_runtime_config

    fallback = get_runtime_config().daily_budget_fallback_provider
    if not fallback or fallback == provider:
        return False
    if daily_budget(fallback) > 0 and usage_today(fallback) >= daily_budget(fallback):
        return False

    logger.warning("%s reported its daily quota exhausted; falling back to %s", provider, fallback)
    _record_fallback_engaged(
        provider,
        fallback,
        reason=(
            f"{provider} reported its daily quota exhausted{f' ({detail})' if detail else ''} "
            f"after {used_before} calls from this server"
        ),
    )
    return True


def has_headroom(estimated_calls: int = 3) -> bool:
    """Whether a turn about to start can be afforded, checked against
    whichever provider effective_provider() says will actually serve it -
    so a request is only refused once neither the live provider nor its
    configured budget fallback has room left.

    estimated_calls defaults to the worst case for one turn (router +
    generation + contribution classifier) so the budget is checked against
    what the turn might cost rather than the single call that would trip it
    mid-answer, which would leave the user with a half-finished response.
    """
    provider = effective_provider()
    budget = daily_budget(provider)
    if budget <= 0:
        # No ceiling configured - the usual case for a local model, which has
        # no external quota to protect.
        return True
    return remaining(provider) >= estimated_calls
