"""Reviewed-answer store for repeated questions.

Every answered question is recorded here and served again only once an admin
has approved it (see db/models.CachedAnswer). The admin may correct the text
first, which is how a wrong answer gets fixed once instead of being repeated
to every student who asks the same thing.

Motivation: every chat turn costs 2-3 Gemini calls against a per-day free-tier
quota, while embeddings run locally and cost nothing. So paying one local
embedding to skip a whole LLM round trip is close to free, and in a study
programme Q&A bot the same handful of questions ("when is the deadline") get
asked over and over - not least because the UI ships suggested-question
buttons that users click directly.

Two lookup tiers:
  1. exact match on normalized text - always safe.
  2. embedding cosine similarity above SIMILARITY_THRESHOLD.

On the threshold: the dangerous case is not an unrelated question, it is the
same question shape with a different entity ("deadline for EU applicants" vs
"...for non-EU applicants"), which needs a DIFFERENT answer but embeds very
closely. Measured on this corpus's own embedding model (bge-large-en-v1.5):

    non-EU vs EU deadline      0.8919   <- must NOT hit
    thesis ECTS phrasings      0.8658   <- same answer, tolerable miss
    "deadline non eu" variants 0.9376 - 0.9835   <- should hit

The two classes overlap, so no threshold is perfect; 0.94 sits above every
observed different-answer pair with margin, and still catches real
paraphrases. Erring high is the right bias: a cache miss costs one LLM call,
a false hit gives a confidently wrong answer.
"""

import json
import re

from sqlalchemy.orm import Session

from db.models import AnswerStatus, CachedAnswer

SIMILARITY_THRESHOLD = 0.94

# Cap the brute-force scan. Well beyond a study programme's realistic distinct
# question count, and keeps the similarity pass trivially cheap either way.
_MAX_CANDIDATES = 2000


def _normalize(question: str) -> str:
    """Casefold and collapse punctuation/whitespace so trivial variations
    ("Deadline?" vs "deadline") share an exact-match key."""
    return re.sub(r"[^a-z0-9]+", " ", question.casefold()).strip()


def _cosine(a: list[float], b: list[float]) -> float:
    # Both sides come from the same normalized-embedding path (see
    # _LocalEmbeddings' normalize_embeddings=True), so a plain dot product is
    # already the cosine.
    return sum(x * y for x, y in zip(a, b))


def lookup(session: Session, question: str, embedding: list[float]) -> CachedAnswer | None:
    """Find a reviewed answer for this question, or None.

    Only APPROVED rows are eligible. An unreviewed answer is exactly the thing
    this gate exists to keep out of circulation: replaying it would take a
    single bad generation and hand it to everyone who asks the same question
    afterwards.
    """
    approved = session.query(CachedAnswer).filter(CachedAnswer.status == AnswerStatus.APPROVED)

    normalized = _normalize(question)
    exact = approved.filter(CachedAnswer.question_normalized == normalized).first()
    if exact is not None:
        return exact

    best: CachedAnswer | None = None
    best_score = SIMILARITY_THRESHOLD
    for row in approved.order_by(CachedAnswer.id.desc()).limit(_MAX_CANDIDATES):
        score = _cosine(embedding, json.loads(row.embedding))
        if score >= best_score:
            best, best_score = row, score
    return best


def store(
    session: Session,
    question: str,
    embedding: list[float],
    answer: str,
    sources: list[dict],
    retrieval: list[dict],
    origin: str | None = None,
) -> None:
    """Record an answered question for review. Stored as PENDING, so it is not
    served to anyone until an admin has checked it."""
    normalized = _normalize(question)
    # One row per distinct question: re-asking something already in the queue
    # should not add a second copy for the admin to review.
    if session.query(CachedAnswer).filter(CachedAnswer.question_normalized == normalized).first():
        return

    session.add(
        CachedAnswer(
            question=question,
            question_normalized=normalized,
            embedding=json.dumps(embedding),
            answer=answer,
            original_answer=answer,
            sources_json=json.dumps(sources),
            retrieval_json=json.dumps(retrieval),
            status=AnswerStatus.PENDING,
            origin=origin,
        )
    )
    session.commit()


def record_hit(session: Session, row: CachedAnswer) -> None:
    row.hit_count += 1
    session.commit()


def invalidate_all() -> int:
    """Send every approved answer back for re-review. Returns how many moved.

    Called whenever the corpus changes (document added/removed, submission
    approved or revoked): an answer is only as valid as the chunks it was
    generated from, and one that outlives its source is exactly the failure
    this system is otherwise built to avoid.

    This demotes rather than deletes. The approved text is often an admin's own
    correction, so throwing it away would discard the very work this queue
    exists to collect - and silently, at that. Demoted rows stop being served
    immediately and reappear in the review queue, where the admin can confirm
    they still hold against the new documents.
    """
    from db.models import SessionLocal

    session = SessionLocal()
    try:
        moved = (
            session.query(CachedAnswer)
            .filter(CachedAnswer.status == AnswerStatus.APPROVED)
            .update(
                {"status": AnswerStatus.PENDING, "reviewed_at": None},
                synchronize_session=False,
            )
        )
        session.commit()
        return moved
    finally:
        session.close()
