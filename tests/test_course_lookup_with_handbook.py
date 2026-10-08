"""A catalogue answer about one specific course keeps the module-handbook
search that runs alongside it; a listing does not wait for it."""

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from config import settings
from graph import nodes


class _Retrieval:
    def __init__(self, docs):
        self.docs, self.cancelled = docs, False

    def result(self):
        return self.docs

    def cancel(self):
        self.cancelled = True


def _run(monkeypatch, catalog_text, docs):
    retrieval = _Retrieval(docs)
    monkeypatch.setattr(nodes, "_SpeculativeRetrieval", lambda query, filter_: retrieval)
    monkeypatch.setattr(
        nodes,
        "_route_with_tools",
        lambda question: {
            "retrieved_docs": [Document(page_content=catalog_text, metadata={"source_id": "catalog"})],
            "direct_answer": None,
            "awaiting_semester_number": False,
        },
    )
    result = nodes.retrieve_node({"messages": [HumanMessage(content="How is Advanced Microeconomics taught?")]})
    return result, retrieval


def _handbook(score):
    return Document(
        page_content="[Module handbook | wir874 - Advanced Microeconomics] Course or seminar 4 SWS 56 h",
        metadata={"source_id": "Module_handbook", "_rerank_score": score},
    )


def test_one_course_gets_its_handbook_passages(monkeypatch):
    result, retrieval = _run(monkeypatch, "Matching courses (1 in total - ...):\n- Advanced Microeconomics", [_handbook(0.9)])
    assert [d.metadata["source_id"] for d in result["retrieved_docs"]] == ["catalog", "Module_handbook"]
    assert not retrieval.cancelled


def test_irrelevant_passages_are_not_added(monkeypatch):
    weak = _handbook(settings.retrieval_relevance_threshold / 10)
    result, _ = _run(monkeypatch, "Matching courses (1 in total - ...):\n- Advanced Microeconomics", [weak])
    assert [d.metadata["source_id"] for d in result["retrieved_docs"]] == ["catalog"]


def test_a_listing_does_not_wait_for_documents(monkeypatch):
    result, retrieval = _run(monkeypatch, "Matching courses (4 in total - ...):\n- a\n- b\n- c\n- d", [_handbook(0.9)])
    assert [d.metadata["source_id"] for d in result["retrieved_docs"]] == ["catalog"]
    assert retrieval.cancelled


def test_a_section_matched_twice_is_given_to_the_model_once(monkeypatch):
    from langchain_core.messages import AIMessage

    seen = {}

    class RecordingLlm:
        def invoke(self, messages):
            seen["prompt"] = "\n".join(str(m.content) for m in messages)
            return AIMessage(content="answer")

    monkeypatch.setattr(nodes, "get_llm", lambda: RecordingLlm())
    monkeypatch.setattr(nodes, "_with_resilience", lambda llm, **kw: llm)
    monkeypatch.setattr(nodes, "_with_fallback", lambda llm, **kw: llm)
    monkeypatch.setattr(nodes, "get_expired_source_ids", lambda: {})
    parent = "[Module handbook | inf536] WHOLE SECTION Lecture 2 Exercises 2"
    docs = [
        Document(page_content="first chunk", metadata={"source_id": "hb", "parent_content": parent}),
        Document(page_content="second chunk", metadata={"source_id": "hb", "parent_content": parent}),
    ]
    nodes.generate_node({"retrieved_docs": docs, "messages": [HumanMessage(content="q")]})

    assert seen["prompt"].count("WHOLE SECTION") == 1
    assert "[2] [source: hb] second chunk" in seen["prompt"]
