"""A short weekly summary for the admins, so a problem shows up without
anyone opening the admin panel: how much the assistant was used, what it
could not answer, what students rated down, how the review queue stands,
the latest golden-set score and whether documents contradict each other.

Sent on Mondays from scripts/maintenance.py (after Sunday's golden-set run).

Usage:
    python scripts/weekly_report.py            # print it
    python scripts/weekly_report.py --notify   # also send it to Telegram
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import AnswerStatus, CachedAnswer, EvalRun, QueryLog, SessionLocal  # noqa: E402


def build_report(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    session = SessionLocal()
    try:
        rows = session.query(QueryLog).filter(QueryLog.created_at >= since).all()
        unanswered = [r.question.strip() for r in rows if not r.answered]
        down = sum(1 for r in rows if r.rating == -1)
        up = sum(1 for r in rows if r.rating == 1)
        cached = sum(1 for r in rows if r.served_from_cache)
        pending = session.query(CachedAnswer).filter(CachedAnswer.status == AnswerStatus.PENDING).count()
        flagged = sum(1 for a in session.query(CachedAnswer).filter(CachedAnswer.downvotes > 0).all() if a.is_flagged)
        last_eval = session.query(EvalRun).order_by(EvalRun.created_at.desc()).first()
    finally:
        session.close()

    lines = [
        f"Weekly summary ({since:%d %b} - {now:%d %b %Y})",
        f"Questions: {len(rows)} ({len({r.thread_id for r in rows})} conversations), "
        f"{cached} answered from approved answers",
        f"Not answered from the documents: {len(unanswered)}",
    ]
    for question, count in Counter(q[:80] for q in unanswered).most_common(5):
        lines.append(f"  - {question}" + (f" ({count}x)" if count > 1 else ""))
    lines.append(f"Ratings: {up} helpful, {down} unhelpful")
    lines.append(f"Review queue: {pending} pending" + (f", {flagged} rated unhelpful since review" if flagged else ""))
    if last_eval:
        failed = json.loads(last_eval.failed_ids_json or "[]")
        lines.append(
            f"Golden set ({last_eval.created_at:%d %b}): {last_eval.passed}/{last_eval.total}"
            + (f", failed: {', '.join(failed[:5])}" if failed else "")
        )
    try:
        from scripts.check_contradictions import _documents, find_conflicts

        conflicts = find_conflicts(_documents())
        lines.append(
            "Documents: no contradictions" if not conflicts else f"Documents: contradict on {', '.join(conflicts)}"
        )
    except Exception as exc:  # noqa: BLE001 - the summary still goes out
        lines.append(f"Documents: contradiction check failed ({exc})")
    return "\n".join(lines)


def main() -> int:
    text = build_report()
    print(text)
    if "--notify" in sys.argv:
        from api.telegram_bot import _notify_admins

        _notify_admins(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
