"""Greetings and "what can you do" messages get a welcome instead of the
"documents do not contain" refusal; real questions are left alone."""

import pytest
from langchain_core.messages import HumanMessage

from graph import nodes


@pytest.mark.parametrize("message", ["hi", "Hi!", "How are you?", "Wie geht es dir?", "What else can I ask you?", "Thanks, that's helpful."])
def test_conversational_messages_get_a_welcome(message):
    reply = nodes._conversational_reply(message)
    assert reply and "Applied Economics and Data Science" in reply


def test_a_german_greeting_is_answered_in_german():
    assert "Studiengang" in nodes._conversational_reply("Hallo, was kannst du mir beantworten?")


@pytest.mark.parametrize("message", [
    "Hi, when is the application deadline?",
    "Hello, how many ECTS is the thesis?",
    "Thanks. Now tell me the resit rules for exams",
    "How do I apply?",
])
def test_real_questions_are_not_treated_as_small_talk(message):
    assert nodes._conversational_reply(message) is None


def test_the_welcome_needs_no_llm_call(monkeypatch):
    monkeypatch.setattr(nodes, "_route_with_tools", lambda q: pytest.fail("router called"))
    monkeypatch.setattr(nodes, "_SpeculativeRetrieval", lambda *a: pytest.fail("retrieval started"))
    result = nodes.retrieve_node({"messages": [HumanMessage(content="hi")]})
    assert result["direct_answer"].startswith("Hi!")


@pytest.mark.parametrize("question, rewritten", [
    ("Am I on track to graduate, and what should I focus on to finish my degree?", True),
    ("What do I still need to graduate?", True),
    ("When do graduates usually find jobs?", False),
    ("My ECTS Tracker progress (60/120 ECTS completed): am I on track?", False),
])
def test_personal_progress_questions_search_the_graduation_requirements(question, rewritten):
    assert (nodes._retrieval_query_for(question, "DEFAULT") == nodes._GRADUATION_QUERY) is rewritten


def test_small_talk_skips_contribution_detection(monkeypatch):
    from langchain_core.messages import AIMessage

    monkeypatch.setattr(nodes, "could_be_a_contribution", lambda text: pytest.fail("gate ran"))
    state = {"messages": [HumanMessage(content="thanks a lot"), AIMessage(content="You're welcome!")]}
    assert nodes.detect_contribution_node(state) == {"detected_contribution": None}


def test_a_follow_up_searches_with_itself_and_the_previous_question():
    from langchain_core.messages import AIMessage

    messages = [
        HumanMessage(content="Do I need a residence permit as a non-EU student?"),
        AIMessage(content="Yes. You also register at the Bürgerbüro within two weeks."),
        HumanMessage(content="Where do I apply for it?"),
    ]
    query = nodes._build_retrieval_query(messages)
    assert query.splitlines()[0] == "Where do I apply for it?"
    assert "residence permit" in query and "Bürgerbüro" not in query


def test_german_campus_words_get_their_english_terms_appended():
    assert nodes._with_campus_terms("How much does a pizza cost in the Mensa?") == "How much does a pizza cost in the Mensa? (canteen)"
    assert "re-registration" in nodes._with_campus_terms("When is the Rückmeldung deadline?")
    # Already in English: nothing appended.
    assert nodes._with_campus_terms("How much does a pizza cost in the canteen?") == "How much does a pizza cost in the canteen?"
