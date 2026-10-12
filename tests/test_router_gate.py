"""graph/nodes.py's _could_need_a_tool: the cheap check that lets a question
skip the routing call when it cannot need a routing tool.

ROUTED_BY_DOTS is every golden-set question the production router
(dots-3-note) sent to a tool on 2026-10-12, one routing call per question.
The gate must let all of them through but one: the thesis credit-points
question, which the regulations answer as well as the catalog (that case
passes with the router skipped). On the same run the gate skipped 64 of the
111 questions."""

import json
from pathlib import Path

from graph import nodes

ROUTED_BY_DOTS = {
    "application-deadline-eu-eea", "application-deadline-germany", "application-deadline-multi-category",
    "application-deadline-non-eu", "application-deadline-unqualified", "compulsory-course-economics",
    "compulsory-course-epe", "contribution-not-flagged-question", "curriculum-listing-generic", "de-compulsory",
    "de-deadline-non-eu", "de-thesis-ects", "deadline-status-relative-to-today", "exam-office-contact",
    "first-semester-typical-courses", "german-enumeration-compulsory", "german-taught-courses",
    "handbook-inf536-class-types", "handbook-wir874-contact-hours", "handbook-wir894-teaching-format",
    "mt-deadline-then-eu", "person-lookup-who-is", "professor-lookup-ci1", "professor-lookup-ci2",
    "professor-lookup-epe-abbreviation", "professor-multiple-courses", "professor-roster", "thesis-ects",
}
ANSWERED_WITHOUT_THE_ROUTER = {"precedence-thesis-credit-points"}


def _cases():
    return {c["id"]: c for c in json.loads(Path("tests/golden_qa.json").read_text(encoding="utf-8"))}


def test_every_question_the_router_sends_to_a_tool_passes_the_gate():
    cases = _cases()
    blocked = [cid for cid in ROUTED_BY_DOTS if not nodes._could_need_a_tool(cases[cid]["question"])]
    assert blocked == []


def test_most_document_questions_skip_the_router():
    cases = _cases()
    others = [c for cid, c in cases.items() if cid not in ROUTED_BY_DOTS | ANSWERED_WITHOUT_THE_ROUTER]
    skipped = sum(not nodes._could_need_a_tool(c["question"]) for c in others)
    assert skipped >= 0.75 * len(others)


def test_lecturer_surnames_and_course_abbreviations_count_as_cues(monkeypatch):
    monkeypatch.setattr(nodes, "get_catalog_courses", lambda: [
        {"name": "Econometrics of Policy Evaluation", "professor": "Peter Eppinger"},
        {"name": "Advanced Microeconomics", "professor": "Carsten Helm"},
    ])
    assert nodes._could_need_a_tool("What does Eppinger research?")
    assert nodes._could_need_a_tool("Is EPE hard?")
    assert not nodes._could_need_a_tool("How much is the semester ticket?")


def test_a_skipped_question_makes_no_routing_call(monkeypatch):
    def fail(*a, **kw):
        raise AssertionError("router called")

    monkeypatch.setattr(nodes, "get_router_llm", fail)
    assert nodes._route_with_tools("How much is the Rundfunkbeitrag?") is None
