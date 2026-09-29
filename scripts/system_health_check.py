"""VPS-level health check: disk, memory, and load - alerts the admin
Telegram chat when any crosses a threshold, and again when it recovers.

Why this exists. Every alert elsewhere in this project is about the
application itself (unhandled errors, LLM budget, answer-quality
regressions) - nothing watched the host it runs on. Found live: a
completely unrelated process on this shared VPS spiked its own error log
at a rate that grew disk usage seven percentage points in about two
minutes, with nothing anywhere surfacing it until it was noticed by chance
while doing unrelated log-rotation work.

Deliberately checks the HOST, not just this app's own directories - a
shared VPS running several unrelated projects means "this app is fine" and
"the box is fine" are different questions, and only the second one
protects this app from being taken down by something else's problem.

Alerts once per breach, then stays quiet for ALERT_COOLDOWN_HOURS even if
still breached (a 15-minute cron would otherwise page the same problem
every cycle), and sends one more message when a check recovers. State is
persisted (SystemHealthAlertState) so this survives a process restart
between cron runs, same reasoning as llm_budget.py's own usage counters.

Usage:
    PYTHONPATH=. python scripts/system_health_check.py

Suggested crontab entry (every 15 minutes):
    */15 * * * * cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \\
        scripts/system_health_check.py >> data/backups/system_health.log 2>&1
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import SessionLocal, SystemHealthAlertState  # noqa: E402

DISK_THRESHOLD_PERCENT = 85.0
MEMORY_THRESHOLD_PERCENT = 90.0
# Sustained load above this many times the core count, not an instantaneous
# spike - a brief burst above 1x per core is normal and not worth alerting
# anyone over.
LOAD_THRESHOLD_RATIO = 2.0
ALERT_COOLDOWN_HOURS = 6.0


def read_disk_percent(path: str = "/") -> float:
    usage = shutil.disk_usage(path)
    return usage.used / usage.total * 100


def read_memory_percent() -> float | None:
    """None if /proc/meminfo isn't readable (non-Linux - e.g. local dev on
    macOS) - the check is simply skipped rather than erroring."""
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                value = rest.strip().split()
                if value:
                    info[key] = int(value[0])  # kB
        total = info.get("MemTotal")
        available = info.get("MemAvailable")
        if not total or available is None:
            return None
        return (total - available) / total * 100
    except (FileNotFoundError, OSError, ValueError):
        return None


def read_load_ratio() -> float | None:
    try:
        load_1min = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    cpus = os.cpu_count() or 1
    return load_1min / cpus


def decide_action(
    check_name: str,
    value: float,
    threshold: float,
    prior_state: dict | None,
    now: datetime,
    cooldown_hours: float = ALERT_COOLDOWN_HOURS,
) -> tuple[str | None, dict]:
    """The pure decision: given a fresh reading and the last known state,
    what (if anything) to alert, and what state to persist next. `now` is
    passed in rather than read internally so this is testable without
    patching datetime.now. Returns (message or None, new_state)."""
    breached = value >= threshold
    was_breached = bool(prior_state and prior_state.get("is_breached"))

    if breached:
        last_alerted_at = prior_state.get("last_alerted_at") if prior_state else None
        cooldown_elapsed = (
            last_alerted_at is None
            or (now - last_alerted_at).total_seconds() >= cooldown_hours * 3600
        )
        if cooldown_elapsed:
            return (
                f"{check_name} at {value:.1f} (threshold {threshold:.1f})",
                {"is_breached": True, "last_alerted_at": now},
            )
        return None, {"is_breached": True, "last_alerted_at": last_alerted_at}

    if was_breached:
        return (
            f"{check_name} recovered - now {value:.1f} (threshold {threshold:.1f})",
            {"is_breached": False, "last_alerted_at": None},
        )

    return None, {"is_breached": False, "last_alerted_at": None}


_CHECKS = [
    ("disk", read_disk_percent, DISK_THRESHOLD_PERCENT),
    ("memory", read_memory_percent, MEMORY_THRESHOLD_PERCENT),
    ("load", read_load_ratio, LOAD_THRESHOLD_RATIO),
]


def _load_state(session, check_name: str) -> dict | None:
    row = session.get(SystemHealthAlertState, check_name)
    if row is None:
        return None
    return {"is_breached": row.is_breached, "last_alerted_at": row.last_alerted_at}


def _save_state(session, check_name: str, state: dict) -> None:
    row = session.get(SystemHealthAlertState, check_name)
    if row is None:
        row = SystemHealthAlertState(check_name=check_name)
        session.add(row)
    row.is_breached = state["is_breached"]
    row.last_alerted_at = state["last_alerted_at"]


def main() -> int:
    from api.telegram_bot import _notify_admins

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        for check_name, reader, threshold in _CHECKS:
            value = reader()
            if value is None:
                # Not readable on this platform/host - nothing to check.
                continue

            prior_state = _load_state(session, check_name)
            message, new_state = decide_action(check_name, value, threshold, prior_state, now)
            _save_state(session, check_name, new_state)
            session.commit()

            print(f"{check_name}: {value:.1f} (threshold {threshold:.1f})")
            if message:
                try:
                    _notify_admins(f"VPS health - {message}")
                except Exception:
                    pass
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
