"""Once-a-day Telegram alerts for operational problems that do not stop
answers but degrade them: the answer model's daily quota running low, or
Cloudflare's free allocation being used up so the reranker runs locally.
Without these the first sign was a student noticing slower or odder
answers."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _claim(key: str) -> bool:
    """True for exactly one caller per key and UTC day, across processes."""
    from db.models import OpsAlertSent, SessionLocal

    today = _today()
    session = SessionLocal()
    try:
        claimed = session.execute(
            update(OpsAlertSent).where(OpsAlertSent.key == key, OpsAlertSent.day != today).values(day=today)
        ).rowcount
        if not claimed and session.get(OpsAlertSent, key) is None:
            session.add(OpsAlertSent(key=key, day=today))
            claimed = 1
        session.commit()
        return bool(claimed)
    except IntegrityError:
        session.rollback()
        return False
    except Exception:  # noqa: BLE001 - an alert must never break an answer
        session.rollback()
        logger.warning("Could not record the %s alert", key, exc_info=True)
        return False
    finally:
        session.close()


def alert_once_per_day(key: str, text: str) -> None:
    """Sends `text` to the admin chat unless `key` was already alerted on
    today (UTC). Runs in the background: never blocks or breaks a caller."""

    def send():
        if not _claim(key):
            return
        try:
            from api.telegram_bot import _notify_admins

            _notify_admins(text)
        except Exception:  # noqa: BLE001
            logger.warning("Could not send the %s alert", key, exc_info=True)

    threading.Thread(target=send, daemon=True).start()
