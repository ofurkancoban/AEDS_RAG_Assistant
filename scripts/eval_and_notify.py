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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.telegram_bot import _notify_admins  # noqa: E402
from runtime_config import get_runtime_config  # noqa: E402
from scripts.export_review_cases import mine_review_cases  # noqa: E402
from tests.eval_golden import load_cases, run  # noqa: E402


def main() -> int:
    # Mined first so a review decision made since the last run (an admin
    # correcting or rejecting an answer) is already reflected in this same
    # eval pass, not just the next one. Existing hand-trimmed cases are never
    # touched (overwrite=False) - only genuinely new review outcomes are
    # added. This writes tests/golden_qa_review.json on the machine running
    # the cron job (the VPS); it is not committed to git automatically, so a
    # human still has to pull it down and commit it for CI and future local
    # runs to see it, and to trim any new needs_review case's candidate
    # assertions before they count for anything (see eval_golden.load_cases,
    # which skips needs_review entries).
    mined = mine_review_cases()
    if mined["added"]:
        _notify_admins(
            f"Golden eval: mined {mined['added']} new regression case(s) from "
            f"reviewed answers ({mined['needs_review']} total still need human "
            f"trimming). Pull tests/golden_qa_review.json and commit it."
        )

    provider = get_runtime_config().llm_provider
    cases = load_cases()

    all_passed = run(cases, verbose=False)

    if not all_passed:
        # run() already printed which cases failed and why - this message is
        # deliberately just a pointer to "go look", not a duplicate of that
        # detail, since eval_golden.py's own retrieval report is much more
        # useful for actually diagnosing it than anything that fits in a chat
        # message.
        _notify_admins(
            f"Golden-set eval failed against the live provider ({provider}). "
            f"Run `PYTHONPATH=. python -m tests.eval_golden --verbose` to see "
            f"which cases regressed and why."
        )

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
