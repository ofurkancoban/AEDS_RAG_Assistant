"""db/contribution_gate.py's plain-statement rule: catches new information
the Laya model scores near zero, without passing ordinary questions."""

import pytest

from db.contribution_gate import _looks_like_statement


@pytest.mark.parametrize("text", [
    "The Data Science lab is located in room A14 in the main building.",
    "The Econometrics II resit exam takes place on Dec 12 at 14:00 in Room 402.",
    "Professor Helm's office hours are on Tuesdays from 2 to 4 pm.",
    "Actually the thesis deadline is June 1st, not May 15th.",
])
def test_plain_statements_pass(text):
    assert _looks_like_statement(text)


@pytest.mark.parametrize("text", [
    "What are the application deadlines?",
    "When do I need to re-register for the next semester",  # no "?" but a question
    "Is the thesis worth 30 ECTS",
    "Can you list all compulsory courses for me",
    "Please list all compulsory courses in the programme",
    "Create a plan for next semester",
    "Tell me about the thesis registration process",
    "I want to know the deadlines for EU students",
    "thanks, that helps",          # too short to carry a claim
    "machine learning module",     # keyword search
    "Wann ist die Bewerbungsfrist für das Wintersemester",
])
def test_questions_requests_and_short_messages_do_not_pass(text):
    assert not _looks_like_statement(text)
