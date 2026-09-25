"""Runs a sample of golden_qa.json questions through the real pipeline and
scores each answer with the LLM-judge metrics in rag_metrics.py (faithfulness,
answer relevance, context precision). Slower and more subjective than
eval_golden.py's substring checks - meant for spotting quality regressions
across a config/prompt/retrieval change over a sample of questions, not as a
pass/fail gate.

Usage:
    python -m tests.eval_quality
    python -m tests.eval_quality --sample 10
    python -m tests.eval_quality --filter deadline
"""

import argparse
import json
import uuid
from pathlib import Path

GOLDEN_SET_PATH = Path(__file__).parent / "golden_qa.json"


def _run_and_capture(case: dict) -> tuple[str, str, str]:
    """Runs the case's setup turns (if any) then the actual question through
    the real compiled graph, returning (question, context, answer)."""
    from graph.build_graph import get_compiled_graph
    from langchain_core.messages import HumanMessage

    graph = get_compiled_graph()
    thread_id = f"quality-eval:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    for setup_question in case.get("setup", []):
        graph.invoke({"messages": [HumanMessage(content=setup_question)], "source_id_filter": None}, config=config)

    result = graph.invoke(
        {"messages": [HumanMessage(content=case["question"])], "source_id_filter": None}, config=config
    )
    context = "\n\n".join(
        f"[source: {doc.metadata.get('source_id', 'unknown')}] "
        f"{doc.metadata.get('parent_content') or doc.page_content}"
        for doc in result.get("retrieved_docs", [])
    )
    if not context and result.get("direct_answer"):
        # direct_answer bypasses retrieval entirely (deterministic lookups) -
        # score against the answer itself, since there's no separately
        # retrieved context to compare it to.
        context = result["direct_answer"]
    return case["question"], context, result["messages"][-1].content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=None, help="Only score the first N cases")
    parser.add_argument("--filter", default=None, help="Only run cases whose id contains this substring")
    args = parser.parse_args()

    cases = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    if args.filter:
        cases = [c for c in cases if args.filter in c["id"]]
        if not cases:
            print(f"No golden cases match filter {args.filter!r}")
            return
    if args.sample:
        cases = cases[: args.sample]

    from graph.nodes import get_classifier_llm
    from tests.rag_metrics import score_answer

    judge_llm = get_classifier_llm()
    totals = {"faithfulness": [], "answer_relevance": [], "context_precision": []}

    for case in cases:
        question, context, answer = _run_and_capture(case)
        scores = score_answer(question, context, answer, judge_llm)
        print(f"[{case['id']}]")
        print(
            f"  faithfulness={scores['faithfulness']}  "
            f"answer_relevance={scores['answer_relevance']}  "
            f"context_precision={scores['context_precision']}"
        )
        if scores.get("notes"):
            print(f"  notes: {scores['notes']}")
        for key in totals:
            if scores.get(key) is not None:
                totals[key].append(scores[key])

    print()
    for key, values in totals.items():
        if values:
            print(f"avg {key}: {sum(values) / len(values):.2f} (n={len(values)})")
        else:
            print(f"avg {key}: n/a (no parseable scores)")


if __name__ == "__main__":
    main()
