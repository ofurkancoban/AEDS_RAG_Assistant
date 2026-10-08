"""Bring the answer review queue up to date before an admin works through it.

- A pending answer built on a document that is no longer in the corpus (the
  2023 examination regulations, replaced by the 2026 version) is asked again
  through the current pipeline, so the admin approves today's answer rather
  than one from a superseded source. The question, its cache key and its
  review status are kept.
- A pending entry that should never be served to another person (a
  student's own ECTS Tracker progress, small talk) is marked rejected with a
  note saying why; nothing is deleted.

Calls the live LLM provider once per regenerated answer (about three
requests each). Run on the server: PYTHONPATH=. python scripts/refresh_review_queue.py
Add --dry-run to only list what would change.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import AnswerStatus, CachedAnswer, IngestedDocument, SessionLocal  # noqa: E402
from db.semantic_cache import is_reusable_question  # noqa: E402


def _current_sources(session) -> set[str]:
    return {Path(row.filename).stem for row in session.query(IngestedDocument.filename).all()} | {"catalog"}


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    session = SessionLocal()
    try:
        current = _current_sources(session)
        pending = session.query(CachedAnswer).filter(CachedAnswer.status == AnswerStatus.PENDING).all()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for row in pending:
            if not is_reusable_question(row.question):
                print(f"reject  #{row.id}: {row.question[:60]!r} (personal or small talk)")
                if not dry_run:
                    row.status = AnswerStatus.REJECTED
                    row.admin_note = (
                        f"Rejected automatically {stamp}: a student's own progress or small talk, "
                        "never served to anyone else."
                    )
                continue

            used = {s.get("source_id") for s in json.loads(row.sources_json or "[]")}
            gone = sorted(s for s in used if s and s not in current)
            if not gone:
                continue
            print(f"refresh #{row.id}: {row.question[:60]!r} (no longer in the corpus: {', '.join(gone)})")
            if dry_run:
                continue
            from graph.build_graph import run_chat

            result = run_chat(thread_id=f"review-refresh:{uuid.uuid4()}", question=row.question)
            row.answer = result["answer"]
            row.original_answer = result["answer"]
            row.sources_json = json.dumps(result["sources"], default=str)
            row.retrieval_json = json.dumps(result.get("retrieval", []), default=str)
            row.admin_note = f"Regenerated {stamp}: the earlier answer used {', '.join(gone)}, which was replaced."
            session.commit()

        session.commit()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
