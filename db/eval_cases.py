"""Eval cases written by an admin from the Question Log.

A wrong answer seen in the log becomes a test: the question exactly as it
was sent (a widget question keeps its progress block, so the case
reproduces what the model saw), with the facts the answer must contain or
must not contain. Cases go to the same drafts file as the review-queue
cases (scripts/export_review_cases.py), not to tests/, which every deploy
replaces. Unlike those drafts an admin wrote these assertions, so they are
not marked needs_review: the weekly golden run on the server uses them at
once, and scripts/pull_eval_cases.py copies them into the committed set.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from config import settings

_lock = threading.Lock()


def drafts_path() -> Path:
    return settings.documents_dir.parent / "eval" / "case_drafts.json"


def case_id(query_log_id: int) -> str:
    return f"log-{query_log_id}"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def existing_ids() -> set[str]:
    try:
        return {case["id"] for case in _read(drafts_path())}
    except (OSError, ValueError):
        return set()


def save_case(case: dict) -> None:
    """Adds or replaces the case with the same id."""
    path = drafts_path()
    with _lock:
        cases = {c["id"]: c for c in _read(path)}
        cases[case["id"]] = case
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(
            json.dumps(sorted(cases.values(), key=lambda c: c["id"]), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
