"""Retrieval-only eval over the golden set: no LLM calls, so no quota and the
same result every run.

For each golden case it runs the real hybrid search and rerank and checks two
things about the passages that would reach the model:

- context recall: every fact the case expects in the answer
  (expected_contains) appears in those passages, so the model at least had
  what it needed;
- source hit: the documents the case names (expected_source_ids) are among
  them.

Multi-turn cases (with "setup" messages) and German questions are skipped:
the first depends on conversation state, the second needs the LLM
translation step before search. So is a case marked "retrieval": false (an
off-topic question the model must refuse: there is nothing to retrieve).

A case answered by a router tool in production (application deadlines, the
examinations office, the course catalog) names that call in "tool_call";
its facts are checked against the tool's output instead of the search,
which never sees that data.

Usage:
    python -m tests.eval_retrieval
    python -m tests.eval_retrieval --report retrieval.json
"""

import argparse
import json
import sys
from pathlib import Path

from tests.eval_golden import _matches, _normalize_for_matching, load_cases


def evaluate(cases: list[dict]) -> list[dict]:
    from db.chroma_client import hybrid_search
    from db.reranker import rerank
    from graph.nodes import _TOOL_NAME_TO_FUNC, _conversational_reply, _looks_german, _with_campus_terms
    from runtime_config import get_runtime_config

    config = get_runtime_config()
    rows = []
    for case in cases:
        # Small talk is answered before any search, so it has nothing to measure.
        if case.get("setup") or case.get("retrieval") is False:
            continue
        if _looks_german(case["question"]) or _conversational_reply(case["question"]):
            continue
        facts = case.get("expected_contains", [])
        if case.get("tool_call"):
            call = case["tool_call"]
            output = _normalize_for_matching(_TOOL_NAME_TO_FUNC[call["name"]].invoke(call.get("args", {})))
            missing = [term for term in facts if not _matches(term, output)]
            rows.append(
                {
                    "id": case["id"],
                    "recall": not missing and bool(facts),
                    "has_facts": bool(facts),
                    "missing": missing,
                    "source_hit": None,
                    "retrieved": [f"tool:{call['name']}"],
                }
            )
            continue
        # The same query production searches with (campus terms appended).
        query = _with_campus_terms(case["question"])
        docs = rerank(query, hybrid_search(query, k=config.retrieval_top_k), config.rerank_top_k)
        context = _normalize_for_matching(
            "\n".join(doc.metadata.get("parent_content") or doc.page_content for doc in docs)
        )
        retrieved = {doc.metadata.get("source_id") for doc in docs}
        missing = [term for term in facts if not _matches(term, context)]
        sources = case.get("expected_source_ids")
        source_hit = None
        if sources:
            source_hit = all(
                (set(req) & retrieved) if isinstance(req, list) else req in retrieved for req in sources
            )
        rows.append(
            {
                "id": case["id"],
                "recall": not missing and bool(facts),
                "has_facts": bool(facts),
                "missing": missing,
                "source_hit": source_hit,
                "retrieved": sorted(s for s in retrieved if s),
            }
        )
    return rows


def summarize(rows: list[dict]) -> str:
    with_facts = [r for r in rows if r["has_facts"]]
    with_sources = [r for r in rows if r["source_hit"] is not None]
    recall = sum(r["recall"] for r in with_facts)
    hits = sum(bool(r["source_hit"]) for r in with_sources)
    return (
        f"context recall {recall}/{len(with_facts)}, "
        f"source hit {hits}/{len(with_sources)} ({len(rows)} cases)"
    )


# The deploy gate and the nightly check (scripts/maintenance.py) use the same
# floors: measured 2026-10-12 at 73/73 and 59/59.
MIN_RECALL = 0.96
MIN_SOURCE_HIT = 0.96


def shares(rows: list[dict]) -> tuple[float, float]:
    with_facts = [r for r in rows if r["has_facts"]]
    with_sources = [r for r in rows if r["source_hit"] is not None]
    recall = sum(r["recall"] for r in with_facts) / max(1, len(with_facts))
    hits = sum(bool(r["source_hit"]) for r in with_sources) / max(1, len(with_sources))
    return recall, hits


def nightly_check() -> str | None:
    """None when retrieval is at its floors, else an alert naming what the
    search stopped finding - after a document was re-ingested by the source
    refresh, say, rather than at the next deploy or Sunday's golden run."""
    rows = evaluate(load_cases(include_review=False))
    recall, hits = shares(rows)
    if recall >= MIN_RECALL and hits >= MIN_SOURCE_HIT:
        return None
    lines = [f"Retrieval check below its floor: {summarize(rows)}"]
    for row in rows:
        if row["has_facts"] and not row["recall"]:
            lines.append(f"- {row['id']}: missing {row['missing']}")
        elif row["source_hit"] is False:
            lines.append(f"- {row['id']}: expected source not retrieved (got {', '.join(row['retrieved'])})")
    return "\n".join(lines[:15])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=None, help="Write per-case results as JSON to this path")
    parser.add_argument("--min-recall", type=float, default=None, help="Exit 1 if context recall is below this share")
    parser.add_argument("--min-source-hit", type=float, default=None, help="Exit 1 if source hits are below this share")
    args = parser.parse_args()

    rows = evaluate(load_cases(include_review=False))
    for row in rows:
        if row["has_facts"] and not row["recall"]:
            print(f"[NO RECALL] {row['id']} - missing {row['missing']}")
    print(summarize(rows))
    if args.report:
        Path(args.report).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    recall, hits = shares(rows)
    too_low = []
    if args.min_recall is not None and recall < args.min_recall:
        too_low.append(f"context recall {recall:.0%} < {args.min_recall:.0%}")
    if args.min_source_hit is not None and hits < args.min_source_hit:
        too_low.append(f"source hit {hits:.0%} < {args.min_source_hit:.0%}")
    if too_low:
        print("BELOW THRESHOLD: " + "; ".join(too_low))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
