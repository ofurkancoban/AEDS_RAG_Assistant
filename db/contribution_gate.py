import re

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


# Openers that make a message a question or a request rather than a claim.
# English is enough in practice (detect_contribution_node translates German
# to English first); the German forms are kept for direct callers.
_QUESTION_OR_REQUEST_START = re.compile(
    r"^(who|what|when|where|which|why|how|is|are|can|could|do|does|did|should|would|will|may|"
    r"wer|was|wann|wo|welche|welcher|welches|warum|wie|kann|muss|gibt|ist|sind|"
    r"tell|explain|show|list|give|create|make|help|please|i want|i need|i would like)\b",
    re.IGNORECASE,
)
_MIN_STATEMENT_WORDS = 6


def _looks_like_statement(text: str) -> bool:
    """A plain declarative sentence: no question mark, not opening like a
    question or a request, and long enough to carry a claim. Laya scores
    corrections ("Actually X, not Y") well but plain new information ("The lab
    is in room A14") barely at all - 0.03 against a 0.20 threshold - so this
    rule catches the statements it misses. Measured (2026-10-07): recall on 25
    hand-written contributions 15/25 -> 25/25, with 0/76 false passes on real
    questions and non-contributions; on 70 real production messages the gate
    passes 10 instead of 6. Rewording Laya's instruction instead was tried
    and was worse - every variant that caught more also passed far more
    ordinary questions."""
    stripped = text.strip()
    if "?" in stripped or len(re.findall(r"\w+", stripped)) < _MIN_STATEMENT_WORDS:
        return False
    return not _QUESTION_OR_REQUEST_START.match(stripped)


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
    if _looks_like_statement(text):
        return True
    result = _get_router().predict(text, _CONTRIBUTION_QUESTIONS)
    probability = result["answers"]["is_contribution"]["noul"]
    return probability >= settings.contribution_gate_threshold
