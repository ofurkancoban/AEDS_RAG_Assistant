"""Dashes in answers and the reply when nothing relevant was found."""

from langchain_core.messages import HumanMessage

from config import settings
from graph import nodes
from graph.build_graph import _looks_unanswered


def test_dashes_become_plain_hyphens_but_ranges_stay():
    assert nodes._plain_dashes("Yes — there is a colloquium.") == "Yes - there is a colloquium."
    assert nodes._plain_dashes("Grading – six weeks.") == "Grading - six weeks."
    assert nodes._plain_dashes("about 15–25 pages") == "about 15–25 pages"


class _Retrieval:
    def result(self):
        return []

    def cancel(self):
        pass


def test_no_answer_names_who_can_help_in_the_users_language(monkeypatch):
    monkeypatch.setattr(nodes, "_SpeculativeRetrieval", lambda *a: _Retrieval())
    monkeypatch.setattr(nodes, "_route_with_tools", lambda q: None)
    english = nodes.retrieve_node({"messages": [HumanMessage(content="Where can I buy a bicycle?")]})["direct_answer"]
    german = nodes.retrieve_node({"messages": [HumanMessage(content="Wo kann ich ein Fahrrad kaufen?")]})["direct_answer"]
    assert "Examinations Office" in english and "Studierendenwerk" in english
    assert "Prüfungsamt" in german
    assert _looks_unanswered(english) and _looks_unanswered(german)
