"""Runs the golden-set answer-quality eval (tests/eval_golden.py) against
whichever LLM provider is currently live in production, and alerts the admin
Telegram chat only when it finds a regression.

Why this exists. tests/eval_golden.py already exists and catches real
regressions (a document edit, a retrieval/prompt change, a model swap
quietly making answers worse) - but nothing ever ran it except a developer
by hand. A model or document change that silently degraded answer quality
had no way to surface itself; the only signal was a student eventually
noticing.

Why it is NOT run daily or forced onto a fixed provider. It runs through the
real run_chat pipeline against whatever provider the admin panel currently
has live (see runtime_config.py) - the whole point is to test what students
are actually being served, not a synthetic baseline. That means a run spends
real quota: ~46 cases, each 2-3 LLM calls (tool router + generation, some +
the contribution classifier), so on OpenRouter's default 45/day budget one
run alone exhausts the entire day's allowance. This is intentionally
scheduled weekly (see the suggested crontab entry below), at an hour with
effectively no real traffic, so the quota spend is a non-issue by the time
students are awake and the budget has reset by the next UTC day regardless.

Deliberately does NOT switch the live provider itself (e.g. to force Ollama
and dodge the quota question) - that global admin setting is shared with
concurrent real users, and flipping it out from under them for the run's
duration would answer real questions with the wrong model. If Ollama should
be what this checks, switch it there deliberately from the admin panel
before scheduling this against it, the same as any other provider choice.

Usage:
    PYTHONPATH=. python scripts/eval_and_notify.py

Suggested crontab entry (05:00 UTC every Sunday - low traffic, and the
overnight budget reset means Monday morning starts unaffected):
    0 5 * * 0 cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \
        scripts/eval_and_notify.py >> data/backups/eval_golden.log 2>&1
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.telegram_bot import _notify_admins  # noqa: E402
from runtime_config import get_runtime_config  # noqa: E402
from scripts.export_review_cases import mine_review_cases  # noqa: E402
from tests.eval_golden import load_cases, run  # noqa: E402


def main() -> int:
    # Mined first: review decisions and thumbs-down ratings since the last
    # run become draft cases in data/eval/case_drafts.json on the server (not
    # rsynced, so a deploy no longer wipes them). Drafts are not run: a human
    # trims one and moves it into tests/golden_qa_review.json, which is.
    mined = mine_review_cases()
    if mined["added"]:
        _notify_admins(
            f"Golden eval: {mined['added']} new draft case(s) from reviewed or downvoted "
            f"answers ({mined['needs_review']} drafts waiting in data/eval/case_drafts.json). "
            "Trim one and move it into tests/golden_qa_review.json to make it count."
        )

    config = get_runtime_config()
    provider = config.llm_provider
    cases = load_cases()

    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.json"
        all_passed = run(cases, verbose=False, report_path=report_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))

    failed = [row["id"] for row in report if not row.get("passed")]
    passed = len(report) - len(failed)
    _record_run(provider, config.openrouter_model if provider == "openrouter" else None, passed, len(report), failed)

    if not all_passed:
        # The ids say what to look at; run() already printed why each failed,
        # and eval_golden.py --verbose shows the full answers.
        shown = ", ".join(failed[:10]) + (f" and {len(failed) - 10} more" if len(failed) > 10 else "")
        _notify_admins(
            f"Golden-set eval: {passed}/{len(report)} passed against the live provider "
            f"({provider}). Failed: {shown}. Details: data/backups/eval_golden.log, or "
            f"`PYTHONPATH=. python -m tests.eval_golden --verbose`."
        )

    return 0 if all_passed else 1


def _record_run(provider: str, model: str | None, passed: int, total: int, failed: list[str]) -> None:
    """Kept for the admin panel's trend; a failure to record never fails
    the run itself."""
    from db.models import EvalRun, SessionLocal

    session = SessionLocal()
    try:
        session.add(EvalRun(provider=provider, model=model, passed=passed, total=total, failed_ids_json=json.dumps(failed)))
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"could not record the eval run: {exc}")
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
