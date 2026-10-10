"""German questions are recognised as German (so retrieval translates them
and structured answers come back in German), and a translated deadline
answer still raises the passed-deadline flag."""

import pytest

from graph import nodes
from graph.build_graph import _has_passed_deadline


@pytest.mark.parametrize("question", [
    "Was sind die Bewerbungsfristen?",
    "Wo ist die Mensa?",
    "Wie bezahle ich den Semesterbeitrag?",
    "Wer ist die Ansprechperson im Prüfungsamt?",
])
def test_german_questions_are_detected(question):
    assert nodes._looks_german(question)


@pytest.mark.parametrize("question", [
    "What are the application deadlines?",
    "Was the deadline extended in 2025?",
    "What do I do if I die of boredom in the lecture?",
    "How do I get to the Mensa with my ticket?",
    "Can I take my bike on the train with the semester ticket?",
])
def test_english_questions_are_not(question):
    assert not nodes._looks_german(question)


def test_passed_deadline_is_flagged_in_either_language():
    assert _has_passed_deadline("Status: This deadline has already passed - it was 87 days ago.")
    assert _has_passed_deadline("Status: Diese Frist ist bereits abgelaufen - sie war vor 87 Tagen.")
    assert not _has_passed_deadline("Frist: 15. Juli 2027")


def test_structured_answer_is_translated_for_a_german_question(monkeypatch):
    monkeypatch.setattr(nodes, "_translate_answer_to_german", lambda text: f"DE:{text}")

    class _Response:
        tool_calls = [{"name": "lookup_examinations_office_contact", "args": {}}]

    class _Router:
        def invoke(self, _messages):
            return _Response()

    monkeypatch.setattr(nodes, "_with_resilience", lambda runnable: _Router())
    monkeypatch.setattr(nodes, "_with_fallback", lambda runnable, **kw: runnable)
    monkeypatch.setattr(nodes, "get_classifier_llm", lambda: type("L", (), {"bind_tools": lambda self, tools: self})())

    german = nodes._route_with_tools("Wer ist die Ansprechperson im Prüfungsamt?")
    english = nodes._route_with_tools("Who is the contact person at the examinations office?")

    assert german["direct_answer"].startswith("DE:")
    assert not english["direct_answer"].startswith("DE:")
