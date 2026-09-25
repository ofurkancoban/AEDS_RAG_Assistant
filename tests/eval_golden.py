"""Golden-set regression eval for the RAG answer pipeline.

Runs every question in golden_qa.json through the real graph.build_graph.run_chat
(same code path the API uses - real Ollama models, real Chroma retrieval, no
mocking) and checks the final answer for expected/forbidden substrings. This is
not exact-match testing (answers are free-form LLM text); it only checks that a
few key facts are present and that known wrong-record facts are absent, which is
enough to catch the class of regressions found manually during development (a
model swap, a document edit, or a retrieval/prompt change silently degrading
answer quality).

Usage:
    python -m tests.eval_golden
    python -m tests.eval_golden --verbose
    python -m tests.eval_golden --filter language

Requires the same runtime the backend needs: Ollama running locally with the
configured models pulled, and the document corpus already ingested into Chroma
(see README). Each case runs in its own thread_id so answers don't carry
conversation-memory context between unrelated questions.
"""

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

GOLDEN_SET_PATH = Path(__file__).parent / "golden_qa.json"
# Cases mined from the answer-review queue by scripts/export_review_cases.py -
# real questions the model got wrong in production, with the assertions derived
# from what the reviewing admin corrected. Optional: absent until that script
# has been run at least once.
REVIEW_SET_PATH = Path(__file__).parent / "golden_qa_review.json"


def load_cases(include_review: bool = True):
    """The hand-written golden set, plus the review-derived one when present.

    Review cases marked needs_review are skipped: they are auto-generated
    candidates that no human has trimmed yet, so failing on them would mean
    failing on assertions nobody has vouched for.
    """
    cases = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    if not include_review or not REVIEW_SET_PATH.exists():
        return cases

    seen = {case["id"] for case in cases}
    for case in json.loads(REVIEW_SET_PATH.read_text(encoding="utf-8")):
        if case.get("needs_review") or case["id"] in seen:
            continue
        cases.append(case)
    return cases


_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")


def _normalize_for_matching(text: str) -> str:
    """Strip Markdown emphasis markers before substring matching.

    This suite asserts on FACTS, not formatting. Once the assistant began
    bolding the values that answer the question, '**fourth** semester' stopped
    containing the literal substring 'fourth semester' even though the answer
    was exactly right - a formatting change should never be able to fail a
    content assertion.
    """
    return _EMPHASIS_RE.sub("", text).lower()


def _matches(term, haystack: str) -> bool:
    """A term is either a string, or a list of interchangeable alternatives
    (any one of which satisfies it) - used where several wordings are equally
    correct, e.g. 'twice' vs 'two times'."""
    if isinstance(term, list):
        return any(str(option).lower() in haystack for option in term)
    return str(term).lower() in haystack


def check_case(result: dict, case: dict) -> list[str]:
    """Returns a list of human-readable problems, empty if the case passed."""
    answer = result["answer"]
    lowered = _normalize_for_matching(answer)
    problems = []

    for term in case.get("expected_contains", []):
        if not _matches(term, lowered):
            problems.append(f"missing expected term: {term!r}")

    for term in case.get("expected_absent", []):
        if _matches(term, lowered):
            problems.append(f"contains forbidden term: {term!r}")

    # "expected_contribution" checks the auto-flagging side effect (detect_
    # contribution_node), not the answer text - present-but-null means "must
    # NOT be flagged", a string means "must be flagged as exactly this type",
    # and an absent key means this case doesn't care either way.
    if "expected_contribution" in case:
        expected_type = case["expected_contribution"]
        detected = result.get("detected_contribution")
        actual_type = detected["type"] if detected else None
        if actual_type != expected_type:
            problems.append(f"expected_contribution {expected_type!r}, got {actual_type!r}")

    # Retrieval-level check: asserts the right document actually reached the
    # model, separately from whether the model then worded the answer well.
    # Without this a failure is ambiguous - retrieval missing the chunk and
    # generation fumbling a chunk it did receive look identical from the
    # answer text alone, and they need opposite fixes.
    if "expected_source_ids" in case:
        retrieved = {item["source_id"] for item in result.get("retrieval", [])}
        # As with expected_contains, an entry may be a list of interchangeable
        # alternatives. Several facts here are stated in more than one
        # authoritative document (the module handbook and the planning rules
        # both give the thesis ECTS), and naming just one of them would fail a
        # run that answered correctly from the other.
        missing = [
            requirement
            for requirement in case["expected_source_ids"]
            if not (
                set(requirement) & retrieved
                if isinstance(requirement, list)
                else requirement in retrieved
            )
        ]
        if missing:
            problems.append(
                f"retrieval missing source_id(s) {missing} - got {sorted(retrieved) or '[]'}"
            )

    return problems


def run(cases: list[dict], verbose: bool, report_path: Path | None = None) -> bool:
    from graph.build_graph import run_chat

    all_passed = True
    results = []
    # Per-case record of what retrieval actually returned. Written out on
    # request so expected_source_ids can be added to a case from observed
    # behaviour rather than guessed - and so a retrieval regression can be read
    # off a diff of two runs.
    report = []

    for case in cases:
        thread_id = f"eval:{uuid.uuid4()}"
        start = time.monotonic()
        try:
            # "setup" messages (if any) are sent first on the same thread_id to
            # reach a conversational state (e.g. triggering a clarifying
            # question) before the actual question under test - their answers
            # are discarded, only the final answer is checked.
            for setup_question in case.get("setup", []):
                run_chat(thread_id=thread_id, question=setup_question)

            result = run_chat(thread_id=thread_id, question=case["question"])
            answer = result["answer"]
            elapsed = time.monotonic() - start
        except Exception as exc:  # noqa: BLE001 - report as a failed case, don't crash the run
            elapsed = time.monotonic() - start
            print(f"[ERROR] {case['id']} ({elapsed:.1f}s) - {exc}")
            all_passed = False
            results.append((case["id"], False))
            report.append({"id": case["id"], "error": str(exc)})
            continue

        problems = check_case(result, case)
        passed = not problems
        all_passed = all_passed and passed
        results.append((case["id"], passed))
        report.append(
            {
                "id": case["id"],
                "question": case["question"],
                "passed": passed,
                "problems": problems,
                "retrieved_source_ids": sorted(
                    {item["source_id"] for item in result.get("retrieval", [])}
                ),
                "declared_source_ids": case.get("expected_source_ids", []),
                # An empty retrieval is not a fault: questions answered by the
                # SQL tools (courses, deadlines) never touch the vector store,
                # and a source assertion must never be added to those.
                "answered_without_retrieval": not result.get("retrieval"),
                "answer": answer,
            }
        )

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {case['id']} ({elapsed:.1f}s)")
        if not passed:
            for problem in problems:
                print(f"    - {problem}")
        if verbose or not passed:
            snippet = answer if verbose else (answer[:400] + ("..." if len(answer) > 400 else ""))
            print(f"    answer: {snippet}\n")

    print()
    passed_count = sum(1 for _, ok in results if ok)
    print(f"{passed_count}/{len(results)} passed")

    if report_path is not None:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"retrieval report written to {report_path}")

    return all_passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Always print the full answer, even on pass")
    parser.add_argument("--filter", default=None, help="Only run cases whose id contains this substring")
    parser.add_argument(
        "--no-review-cases",
        action="store_true",
        help="Run only the hand-written golden set, skipping cases mined from the review queue",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Write a JSON report of what each case retrieved and answered to this path",
    )
    args = parser.parse_args()

    cases = load_cases(include_review=not args.no_review_cases)
    if args.filter:
        cases = [c for c in cases if args.filter in c["id"]]
        if not cases:
            print(f"No golden cases match filter {args.filter!r}")
            sys.exit(1)

    all_passed = run(cases, args.verbose, Path(args.report) if args.report else None)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
