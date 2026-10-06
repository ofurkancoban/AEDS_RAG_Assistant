"""graph/nodes.py runs document search in parallel with the tool router.
The answer must not change, the progress stages must stay in order, and a
search made unnecessary by a tool answer must not keep the CPU busy."""

import time

import pytest
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

import graph.nodes as nodes
from graph import progress


@pytest.fixture
def stages():
    seen: list[str] = []
    token = progress.set_reporter(seen.append)
    yield seen
    progress.reset_reporter(token)


def _docs(n=3):
    return [Document(page_content=f"passage {i}", metadata={"source_id": f"s{i}", "_rerank_score": 0.9}) for i in range(n)]


@pytest.fixture
def fake_search(monkeypatch):
    calls = {"rerank": 0}
    monkeypatch.setattr(nodes, "_translate_to_english", lambda q: q)

    def slow_search(query, k, filter=None):
        time.sleep(0.3)
        return _docs()

    def slow_rerank(query, docs, top_k):
        calls["rerank"] += 1
        time.sleep(0.3)
        return docs[:top_k]

    monkeypatch.setattr(nodes, "hybrid_search", slow_search)
    monkeypatch.setattr(nodes, "rerank", slow_rerank)
    return calls


def _state(question="What are the thesis rules?"):
    return {"messages": [HumanMessage(content=question)], "source_id_filter": None}


def test_document_path_runs_search_while_the_router_thinks(monkeypatch, fake_search, stages):
    def slow_router(question):
        time.sleep(0.6)
        return None

    monkeypatch.setattr(nodes, "_route_with_tools", slow_router)

    started = time.time()
    result = nodes.retrieve_node(_state())
    elapsed = time.time() - started

    assert [d.page_content for d in result["retrieved_docs"]] == ["passage 0", "passage 1", "passage 2"][:len(result["retrieved_docs"])]
    # Sequential would be 0.6 (router) + 0.3 (search) + 0.3 (rerank) = 1.2s.
    assert elapsed < 1.0, elapsed
    assert stages == [progress.UNDERSTANDING, progress.SEARCHING, progress.RANKING]


def test_tool_answer_reports_no_search_stages_and_skips_the_rerank(monkeypatch, fake_search, stages):
    tool_answer = {"retrieved_docs": [], "direct_answer": "15 July", "awaiting_semester_number": False}
    monkeypatch.setattr(nodes, "_route_with_tools", lambda question: tool_answer)

    assert nodes.retrieve_node(_state("When is the deadline?")) is tool_answer
    time.sleep(0.5)  # let the background search finish

    assert stages == [progress.UNDERSTANDING]
    assert fake_search["rerank"] == 0


def test_a_search_failure_surfaces_on_the_document_path(monkeypatch, stages):
    monkeypatch.setattr(nodes, "_translate_to_english", lambda q: q)
    monkeypatch.setattr(nodes, "_route_with_tools", lambda question: None)

    def broken_search(query, k, filter=None):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(nodes, "hybrid_search", broken_search)

    with pytest.raises(RuntimeError, match="chroma unavailable"):
        nodes.retrieve_node(_state())
