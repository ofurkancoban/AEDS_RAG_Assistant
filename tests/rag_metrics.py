"""Lightweight LLM-judge-based RAG quality metrics: faithfulness, answer
relevance, and context precision. A dependency-light alternative to a full
Ragas/TruLens integration - reuses this project's own already-configured LLM
(qwen2.5:7b via Ollama) as the judge, rather than adding a new framework and
its own LLM-provider adapter layer for what is, underneath, three targeted
questions asked of a judge model.

These are judge-model opinions, not ground truth - useful for spotting
regressions or comparing configurations (e.g. before/after a retrieval or
prompt change) over a sample of questions, not as a certified accuracy score.
"""

import json
import re

from langchain_core.messages import HumanMessage

_JUDGE_PROMPT = (
    "You are evaluating a RAG (retrieval-augmented generation) system's answer "
    "to a user's question, given the context that was retrieved for it.\n\n"
    "Question: {question}\n\n"
    "Retrieved context:\n{context}\n\n"
    "Answer: {answer}\n\n"
    "Rate the answer on three dimensions, each from 0.0 to 1.0:\n"
    "- faithfulness: does every factual claim in the answer appear in the "
    "retrieved context (1.0), or does it include unsupported/fabricated "
    "claims (lower, down to 0.0 if entirely unsupported)?\n"
    "- answer_relevance: does the answer actually address the question asked "
    "(1.0), or does it drift off-topic / answer a different question (lower)?\n"
    "- context_precision: of the retrieved context shown above, how much of "
    "it is actually relevant to answering the question (1.0 = all of it, "
    "lower if much of it is irrelevant noise)?\n\n"
    "Respond with strict JSON only, no other text:\n"
    '{{"faithfulness": <float 0-1>, "answer_relevance": <float 0-1>, '
    '"context_precision": <float 0-1>, "notes": "<one short sentence on the '
    'lowest-scoring dimension>"}}'
)

_MAX_CONTEXT_CHARS = 6000  # keeps the judge prompt itself within a sane size


def score_answer(question: str, context: str, answer: str, judge_llm) -> dict:
    """Returns {"faithfulness": float|None, "answer_relevance": float|None,
    "context_precision": float|None, "notes": str}. Scores are None if the
    judge's output couldn't be parsed as the expected JSON."""
    prompt = _JUDGE_PROMPT.format(question=question, context=context[:_MAX_CONTEXT_CHARS], answer=answer)
    raw = judge_llm.invoke([HumanMessage(content=prompt)]).content

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, AttributeError):
        return {
            "faithfulness": None,
            "answer_relevance": None,
            "context_precision": None,
            "notes": "judge output could not be parsed as JSON",
        }

    return {
        "faithfulness": parsed.get("faithfulness"),
        "answer_relevance": parsed.get("answer_relevance"),
        "context_precision": parsed.get("context_precision"),
        "notes": parsed.get("notes", ""),
    }
