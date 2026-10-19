"""Copies the eval cases admins wrote from the Question Log on the server
(db/eval_cases.py) into the committed tests/golden_qa_review.json, so they
also run locally and in the deploy's retrieval check, and survive a server
rebuild. Review-queue drafts that still need a human (needs_review) stay on
the server.

Usage (from the repo root, then commit tests/golden_qa_review.json):
    PYTHONPATH=. .venv/bin/python scripts/pull_eval_cases.py
    PYTHONPATH=. .venv/bin/python scripts/pull_eval_cases.py --from case_drafts.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.eval_golden import GOLDEN_SET_PATH, REVIEW_SET_PATH  # noqa: E402

REMOTE = "root@158.220.124.164:/root/AEDS_RAG_Assistant/data/eval/case_drafts.json"


def merge(drafts: list[dict], committed: list[dict], golden_ids: set[str]) -> tuple[list[dict], list[str]]:
    have = {case["id"] for case in committed} | golden_ids
    added = [case for case in drafts if not case.get("needs_review") and case["id"] not in have]
    return committed + added, [case["id"] for case in added]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", help="A local copy of the drafts file instead of the server's")
    args = parser.parse_args()

    if args.source:
        text = Path(args.source).read_text(encoding="utf-8")
    else:
        text = subprocess.run(["ssh", REMOTE.split(":")[0], "cat", REMOTE.split(":", 1)[1]], check=True, capture_output=True, text=True).stdout

    committed = json.loads(REVIEW_SET_PATH.read_text(encoding="utf-8")) if REVIEW_SET_PATH.exists() else []
    golden_ids = {case["id"] for case in json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))}
    merged, added = merge(json.loads(text), committed, golden_ids)
    if not added:
        print("No new admin-written cases.")
        return 0
    REVIEW_SET_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {len(added)} case(s) to {REVIEW_SET_PATH.name}: {', '.join(added)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
