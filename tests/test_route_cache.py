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


def _counting_router(monkeypatch):
    calls = []

    class Router:
        def invoke(self, messages):
            calls.append(messages[-1].content)
            return AIMessage(content="", tool_calls=[{"name": "lookup_examinations_office_contact", "args": {}, "id": "1"}])

    monkeypatch.setattr(nodes, "_with_resilience", lambda runnable, **kw: Router())
    monkeypatch.setattr(nodes, "get_router_llm", lambda: (type("L", (), {"bind_tools": lambda self, t: self})(), None))
    monkeypatch.setattr(nodes, "_with_fallback", lambda runnable, **kw: runnable)
    return calls


def test_a_restart_does_not_empty_the_cache(monkeypatch):
    nodes._ROUTE_CACHE.clear()
    calls = _counting_router(monkeypatch)

    nodes._route_with_tools("Who chairs the examining board?")
    nodes._ROUTE_CACHE.clear()  # what a restart does to the in-memory layer
    nodes._route_with_tools("Who chairs the examining board?")

    assert len(calls) == 1
    nodes._ROUTE_CACHE.clear()


def test_a_changed_router_prompt_or_tools_asks_again(monkeypatch):
    nodes._ROUTE_CACHE.clear()
    calls = _counting_router(monkeypatch)

    nodes._route_with_tools("Who is the examinations office contact person?")
    nodes._ROUTE_CACHE.clear()
    monkeypatch.setattr(nodes, "_router_fingerprint", lambda: "after-a-deploy")
    nodes._route_with_tools("Who is the examinations office contact person?")

    assert len(calls) == 2
    nodes._ROUTE_CACHE.clear()
