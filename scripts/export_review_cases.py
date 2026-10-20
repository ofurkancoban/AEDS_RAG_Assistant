"""Turn the answer-review queue into golden-eval regression cases.

Every time an admin rejects an answer, or corrects one before approving it,
they record something no synthetic test can produce: a real question a real
student asked, together with the fact that the model got it wrong and (for a
correction) what the right answer was. Until now that evidence stayed in the
database and the eval set never grew from it.

This script mines two kinds of review outcome:

  corrected  status=APPROVED with original_answer set. The admin's text is
             ground truth and the model's text is a known-bad answer, so the
             difference between them yields both expected_contains (facts the
             model missed) and expected_absent (facts the model invented).

  rejected   status=REJECTED. There is no corrected text to diff against, so
             no assertions can be derived honestly. The case is still written
             out, with the hard facts from the bad answer listed as candidate
             expected_absent terms and needs_review set, for a human to trim.

Only "hard facts" are extracted - numbers, dates, ECTS/credit values, grades
and capitalised names - because those are what the existing golden set asserts
on and what this model actually gets wrong. Extracting arbitrary prose would
produce assertions that fail on harmless rewording.

It also mines thumbs-down ratings (query_log.rating = -1) on answers that
never reached the review queue: the first question of a conversation, still
personal-free, with the hard facts of the downvoted answer as candidate
expected_absent terms and needs_review set, like a rejection.

New cases go to data/eval/case_drafts.json, not to the committed
tests/golden_qa_review.json: scripts/deploy.sh rsyncs tests/ with --delete
(and leaves data/ alone), so cases mined on the server used to be wiped by
the next deploy. A human trims a draft and moves it into
tests/golden_qa_review.json, which tests/eval_golden.py loads alongside the
hand-written set. A case already in either file is never overwritten, so
hand-trimmed assertions survive re-runs; --overwrite rebuilds drafts only.

Usage:
    PYTHONPATH=. python scripts/export_review_cases.py
    PYTHONPATH=. python scripts/export_review_cases.py --dry-run
    PYTHONPATH=. python scripts/export_review_cases.py --overwrite
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from db.models import AnswerStatus, CachedAnswer, QueryLog, SessionLocal  # noqa: E402

REVIEW_SET_PATH = Path(__file__).resolve().parent.parent / "tests" / "golden_qa_review.json"
DRAFTS_PATH = settings.documents_dir.parent / "eval" / "case_drafts.json"

# Markdown emphasis is stripped before matching by the eval runner, so it must
# be stripped here too or an extracted term would carry markers the runner has
# already removed and could never match.
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")

_FACT_PATTERNS = (
    # dates: "15 July 2026", "July 15, 2026", "2026-07-15", "15.07.2026"
    re.compile(r"\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b"),
    re.compile(r"\b[A-Z][a-z]+\s+\d{1,2},\s*\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
    # quantities that carry a unit: "120 ECTS", "6 credit points", "30 hours"
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ECTS|CP|credit points?|credits?|semesters?|weeks?|months?|hours?|years?)\b", re.IGNORECASE),
    # language levels and grades: "B2", "C1", "grade 2.5"
    re.compile(r"\b[ABC][12]\b"),
    re.compile(r"\bgrade\s+\d(?:[.,]\d)?\b", re.IGNORECASE),
    # legal references the model likes to fabricate
    re.compile(r"§\s*\d+[a-z]?"),
    re.compile(r"\b(?:Section|Article|Paragraph)\s+\d+\b", re.IGNORECASE),
    # multi-word proper nouns: course, module and person names
    re.compile(r"\b(?:[A-Z][a-zA-Z]+\s+){1,4}[A-Z][a-zA-Z]+(?:\s+I{1,3})?\b"),
)

# Sentence-initial capitals and boilerplate would otherwise be picked up as
# proper nouns by the last pattern above.
_STOP_TERMS = {
    "the", "this", "that", "these", "those", "there", "here", "however",
    "applied economics", "data science", "master", "msc", "m.sc",
    "university of oldenburg", "i don't know", "i do not know",
}


def _strip_markdown(text: str) -> str:
    return _EMPHASIS_RE.sub("", text)


def _is_meaningful(term: str) -> bool:
    lowered = term.strip().lower()
    if len(lowered) < 2 or lowered in _STOP_TERMS:
        return False
    # A capitalised phrase that is really just a sentence opener ("The
    # programme requires") adds noise, not signal.
    return not any(lowered.startswith(f"{stop} ") for stop in _STOP_TERMS)


def extract_facts(text: str) -> list[str]:
    """Pull the assertable hard facts out of an answer, in order of appearance
    and without duplicates."""
    cleaned = _strip_markdown(text)
    found: dict[str, None] = {}
    for pattern in _FACT_PATTERNS:
        for match in pattern.finditer(cleaned):
            term = match.group(0).strip()
            if _is_meaningful(term):
                found.setdefault(term, None)
    return list(found)


def _diff_facts(corrected: str, original: str) -> tuple[list[str], list[str]]:
    """Facts the correction added, and facts it removed.

    Compared case-insensitively so a capitalisation change alone does not read
    as a factual difference.
    """
    corrected_facts = extract_facts(corrected)
    original_facts = extract_facts(original)
    corrected_lower = {f.lower() for f in corrected_facts}
    original_lower = {f.lower() for f in original_facts}
    added = [f for f in corrected_facts if f.lower() not in original_lower]
    removed = [f for f in original_facts if f.lower() not in corrected_lower]
    return added, removed


def build_case(row: CachedAnswer) -> dict | None:
    """Build one eval case from a reviewed answer, or None if the row carries
    no usable evidence."""
    from db.semantic_cache import is_reusable_question

    # A widget question (the student's own course list), small talk or a
    # menu question is rejected to keep it out of the shared cache, not
    # because the answer was wrong: 12 of 13 drafts on 2026-10-20 were these,
    # with "120 ECTS" and correct course names as candidate wrong facts.
    if row.status == AnswerStatus.REJECTED and not is_reusable_question(row.question):
        return None
    sources = json.loads(row.sources_json or "[]")
    # sources_json holds either bare source ids or {"source_id": ...} objects
    # depending on which code path wrote it.
    source_ids = sorted(
        {s["source_id"] if isinstance(s, dict) else s for s in sources if s}
    )

    if row.status == AnswerStatus.APPROVED and row.original_answer:
        added, removed = _diff_facts(row.answer, row.original_answer)
        if not added and not removed:
            # The admin's edit was purely cosmetic; nothing to assert.
            return None
        case = {
            "id": f"review-corrected-{row.id}",
            "question": row.question,
            "expected_contains": added,
            "expected_absent": removed,
            "notes": (
                "Derived from admin correction of answer #%d. The model's "
                "original answer was corrected by a reviewer; the terms above "
                "are the factual difference between the two." % row.id
            ),
        }
    elif row.status == AnswerStatus.REJECTED:
        case = {
            "id": f"review-rejected-{row.id}",
            "question": row.question,
            "expected_contains": [],
            "expected_absent": extract_facts(row.answer),
            "needs_review": True,
            "notes": (
                "Derived from admin rejection of answer #%d. No corrected text "
                "exists, so expected_absent lists the hard facts from the "
                "rejected answer as candidates only - a human must delete any "
                "that were actually correct before this case is trustworthy. "
                "Admin note: %s" % (row.id, row.admin_note or "(none)")
            ),
        }
    else:
        return None

    if source_ids:
        case["expected_source_ids"] = source_ids
    return case


def build_downvote_case(session, entry: QueryLog) -> dict | None:
    """A draft case from a thumbs-down on an answer, or None when the rating
    carries nothing testable: a follow-up (meaningless without the turns
    before it), a student's own progress or small talk, or an answer that
    is no longer in the conversation history."""
    from db.answer_flags import _answer_text
    from db.semantic_cache import is_reusable_question

    first_in_thread = (
        session.query(QueryLog.id).filter(QueryLog.thread_id == entry.thread_id).order_by(QueryLog.id).first()
    )
    if first_in_thread is None or first_in_thread[0] != entry.id:
        return None
    if not is_reusable_question(entry.question):
        return None
    answer = _answer_text(session, entry)
    if not answer:
        return None
    case = {
        "id": f"downvoted-{entry.id}",
        "question": entry.question,
        "expected_contains": [],
        "expected_absent": extract_facts(answer),
        "needs_review": True,
        "notes": (
            "Derived from a student's thumbs-down on query #%d (%s). expected_absent "
            "lists the hard facts of the downvoted answer as candidates only - delete "
            "any that were correct, add what the answer should have said."
            % (entry.id, entry.created_at.strftime("%Y-%m-%d") if entry.created_at else "?")
        ),
    }
    if entry.source_ids:
        case["expected_source_ids"] = sorted({s for s in entry.source_ids.split(",") if s})
    return case


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing() -> list[dict]:
    return _read(REVIEW_SET_PATH) + _read(DRAFTS_PATH)


def mine_review_cases(overwrite: bool = False, dry_run: bool = False) -> dict:
    """The actual work, independent of argparse, so other code (see
    scripts/eval_and_notify.py) can call this directly without going through
    a CLI invocation. Returns the summary counts main() prints."""
    committed = {case["id"] for case in _read(REVIEW_SET_PATH)}
    drafts = {case["id"]: case for case in _read(DRAFTS_PATH)}

    session = SessionLocal()
    try:
        rows = (
            session.query(CachedAnswer)
            .filter(CachedAnswer.status.in_([AnswerStatus.APPROVED, AnswerStatus.REJECTED]))
            .order_by(CachedAnswer.id)
            .all()
        )
        built = [case for case in (build_case(row) for row in rows) if case]
        downvoted = session.query(QueryLog).filter(QueryLog.rating == -1).order_by(QueryLog.id).all()
        reviewed_questions = {case["question"].strip().lower() for case in built}
        for entry in downvoted:
            case = build_downvote_case(session, entry)
            # A reviewed answer to the same question already yields a better
            # case (the admin's correction or rejection).
            if case and case["question"].strip().lower() not in reviewed_questions:
                built.append(case)
    finally:
        session.close()

    added, refreshed, skipped = 0, 0, 0
    for case in built:
        if case["id"] in committed or (case["id"] in drafts and not overwrite):
            skipped += 1
            continue
        if case["id"] in drafts:
            refreshed += 1
        else:
            added += 1
        drafts[case["id"]] = case

    merged = sorted(drafts.values(), key=lambda c: c["id"])
    needs_review = sum(1 for c in merged if c.get("needs_review"))

    if not dry_run:
        DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRAFTS_PATH.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    return {
        "examined": len(rows),
        "buildable": len(built),
        "added": added,
        "refreshed": refreshed,
        "skipped": skipped,
        "total": len(merged),
        "needs_review": needs_review,
        "sample": merged[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written, change nothing")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rebuild cases that already exist, discarding any hand-trimmed assertions",
    )
    args = parser.parse_args()

    result = mine_review_cases(overwrite=args.overwrite, dry_run=args.dry_run)

    print(f"reviewed answers examined : {result['examined']}")
    print(f"cases buildable           : {result['buildable']}")
    print(f"new                       : {result['added']}")
    print(f"refreshed (--overwrite)   : {result['refreshed']}")
    print(f"kept as-is                : {result['skipped']}")
    print(f"drafts                    : {result['total']} ({result['needs_review']} still need human trimming)")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        for case in result["sample"]:
            print(json.dumps(case, indent=2, ensure_ascii=False))
        return 0

    print(f"\nwrote {DRAFTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
