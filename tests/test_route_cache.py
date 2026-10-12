"""A repeated question reuses the router's decision; the tool still runs."""

from langchain_core.messages import AIMessage

from graph import nodes


def test_the_router_is_asked_once_per_question(monkeypatch):
    nodes._ROUTE_CACHE.clear()
    calls = []

    class Router:
        def invoke(self, messages):
            calls.append(messages[-1].content)
            return AIMessage(content="", tool_calls=[{"name": "lookup_examinations_office_contact", "args": {}, "id": "1"}])

    monkeypatch.setattr(nodes, "_with_resilience", lambda runnable, **kw: Router())
    monkeypatch.setattr(nodes, "get_router_llm", lambda: (type("L", (), {"bind_tools": lambda self, t: self})(), None))
    monkeypatch.setattr(nodes, "_with_fallback", lambda runnable, **kw: runnable)

    first = nodes._route_with_tools("Who is the contact at the examinations office?")
    second = nodes._route_with_tools("who is the contact at the Examinations Office")

    assert len(calls) == 1
    assert first["direct_answer"] == second["direct_answer"]
    nodes._ROUTE_CACHE.clear()
