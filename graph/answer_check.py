"""Statement-level check of a generated answer against its context, run in
the background after the answer has gone out.

The number guard (graph/nodes.py's unsupported_numbers) catches figures the
context does not contain. It cannot catch an answer that misreads the
context: one fee component given as the total, an examining body named
wrongly, a superseded value presented as current, or "the documents do not
say" when they do. A second model call that reads the answer next to its
context can.

Measured 2026-10-15 on 57 stored answers (dots as the checker): it flagged
22 of 27 answers the golden set had failed, and 6 of 30 it had passed, of
which at least 4 were real errors the golden assertions missed (a wrong
total, modules removed in 2026 listed as current, "Prüfungsamt" for the
examining board, a resit rule). It missed a superseded value ("15-20 pages",
the 2023 figure). Median 16s per check, too slow to hold an answer back, so
it runs after the answer is sent and its findings go to the people who
review answers (/review in Telegram, the weekly summary), not to the student.
"""

from __future__ import annotations

import json
import logging
import re
import threading

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings

logger = logging.getLogger(__name__)

CHECK_PROMPT = (
    "You check an assistant's answer against the context it was given. List every statement in the "
    "answer that the context does not support: a figure, date, rule or name the context does not state, "
    "a value the context gives as previous, old or superseded but the answer presents as current, a part "
    "presented as the whole (one fee component given as the total), or a claim that the context lacks "
    "information it does contain. Paraphrase, translation and omissions are fine. Reply with JSON only: "
    '{"unsupported": ["<short quote from the answer> - <why>"]}, an empty list if everything is supported.'
)


def parse_findings(reply: str) -> list[str] | None:
    """The checker's findings, or None when its reply is not the JSON asked for."""
    match = re.search(r"\{.*\}", reply, re.S)
    if not match:
        return None
    try:
        findings = json.loads(match.group(0)).get("unsupported", [])
    except (json.JSONDecodeError, AttributeError):
        return None
    return [str(f) for f in findings if str(f).strip()]


def _with_student_progress(question: str, context: str) -> tuple[str, str]:
    """An ECTS Tracker widget question starts with the student's own course
    list, which the answer is allowed to use. Left inside the question, the
    checker flagged the student's own courses and totals as "not in the
    context" (2026-10-19), so the list is moved into the context."""
    from graph.nodes import student_question

    asked = student_question(question)
    if asked == question:
        return question, context
    progress = question[: question.rfind(asked)].strip()
    progress = re.sub(r"\s*Question:\s*$", "", progress)
    return asked, f"The student's own course progress (from their ECTS Tracker):\n{progress}\n\n{context}"


def check_answer(question: str, context: str, answer: str) -> list[str] | None:
    from graph.nodes import _with_fallback, get_classifier_llm

    llm = _with_fallback(get_classifier_llm())
    question, context = _with_student_progress(question, context)
    reply = llm.invoke(
        [
            SystemMessage(content=CHECK_PROMPT),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:\n{answer}"),
        ],
        config={"callbacks": []},
    ).content
    return parse_findings(reply)


def record(question: str, answer: str, findings: list[str]) -> None:
    from db.models import AnswerCheck, SessionLocal
    from db.semantic_cache import _normalize

    session = SessionLocal()
    try:
        session.add(
            AnswerCheck(
                question=question,
                question_normalized=_normalize(question),
                answer=answer,
                findings_json=json.dumps(findings, ensure_ascii=False),
            )
        )
        session.commit()
    finally:
        session.close()


def _run(question: str, context: str, answer: str) -> None:
    try:
        findings = check_answer(question, context, answer)
        if findings is None:
            logger.warning("answer check: unparseable reply for %r", question[:80])
            return
        record(question, answer, findings)
        if findings:
            logger.warning("answer check: %d unsupported statement(s) for %r", len(findings), question[:80])
    except Exception:  # noqa: BLE001 - a check never affects the answer itself
        logger.warning("answer check failed", exc_info=True)


def check_in_background(question: str, context: str, answer: str) -> None:
    if settings.answer_check == "off":
        return
    threading.Thread(target=_run, args=(question, context, answer), daemon=True, name="answer-check").start()


def latest_findings(question: str) -> list[str] | None:
    """The most recent check's findings for this question, for /review."""
    from db.models import AnswerCheck, SessionLocal
    from db.semantic_cache import _normalize

    session = SessionLocal()
    try:
        row = (
            session.query(AnswerCheck)
            .filter(AnswerCheck.question_normalized == _normalize(question))
            .order_by(AnswerCheck.id.desc())
            .first()
        )
        return json.loads(row.findings_json) if row else None
    finally:
        session.close()
