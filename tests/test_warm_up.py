"""Startup warm-up loads the retrieval models and never stops the app."""


from graph import nodes


def test_warm_up_runs_a_search_and_a_rerank(monkeypatch):
    calls = []
    monkeypatch.setattr(nodes, "hybrid_search", lambda query, k: calls.append("search") or ["doc"])
    monkeypatch.setattr(nodes, "rerank", lambda query, docs, top_k: calls.append("rerank") or docs)
    nodes.warm_up_retrieval()
    assert calls == ["search", "rerank"]


def test_a_failing_warm_up_does_not_raise(monkeypatch):
    def broken(query, k):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(nodes, "hybrid_search", broken)
    nodes.warm_up_retrieval()
