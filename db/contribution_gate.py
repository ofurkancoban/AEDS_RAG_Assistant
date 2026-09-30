from concurrency import once
from config import settings

# "noul" = calibrated yes/no probability (Laya's terminology). Kept short and
# close to Laya's own documented example - an earlier, longer instruction that
# spelled out every excluded category in prose measured much worse (recall
# 0.18 vs 0.64 on the same 74-message eval set) than this one-line phrasing.
_CONTRIBUTION_QUESTIONS = {
    "is_contribution": {
        "type": "noul",
        "instructions": "Does this message state a correction or new fact (not a question)?",
    }
}


@once
def _get_router():
    # Loaded once and kept resident, like the reranker (db/reranker.py) - a
    # 421M/322M param model, reloading it per request would add seconds to
    # every chat turn. preload=True warms both the English and multilingual
    # checkpoints at once instead of stalling the first non-English message.
    from laya import Router

    return Router(preload=True)


def could_be_a_contribution(text: str) -> bool:
    """Cheap pre-filter deciding whether a message is even worth spending an
    LLM call to classify (see detect_contribution_node in graph/nodes.py for
    what happens after this returns true).

    Replaces an earlier regex/keyword heuristic. Measured against a local-LLM
    oracle on 74 hand-labelled English messages: this gate at
    settings.contribution_gate_threshold (0.20) scores precision 0.78 /
    recall 0.93 (F1 0.85), against the old regex's precision 0.67 / recall
    0.96 - fewer wasted LLM calls on non-contributions for a small recall
    cost, which matches this gate's own risk asymmetry (a missed contribution
    still has the explicit "Notify Admin" button as a fallback; a false
    positive burns an LLM call from the daily budget). Re-confirmed on 151
    real chat_history messages (1 real contribution in the sample - too few
    to trust the precision/recall numbers there, but directionally the same:
    fewer false positives than the regex gate at threshold >= 0.35).

    Its multilingual checkpoint underperformed the English one on this task
    in testing (missed real German corrections) - graph/nodes.py's
    detect_contribution_node works around this by translating the message
    to English before calling this function, so this always runs the
    stronger English checkpoint regardless of the message's language. A
    direct caller that skips that translation step gets the weaker
    multilingual checkpoint's accuracy instead.
    """
    result = _get_router().predict(text, _CONTRIBUTION_QUESTIONS)
    probability = result["answers"]["is_contribution"]["noul"]
    return probability >= settings.contribution_gate_threshold
