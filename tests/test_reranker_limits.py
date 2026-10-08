"""The reranker scores only hybrid search's best candidates."""

from langchain_core.documents import Document

from config import settings
from db import reranker


class _Scores:
    def __init__(self):
        self.pairs = []

    def predict(self, pairs):
        self.pairs = pairs
        return [float(len(pairs) - i) for i in range(len(pairs))]


def test_only_the_first_candidates_are_scored(monkeypatch):
    fake = _Scores()
    monkeypatch.setattr(reranker, "get_reranker", lambda: fake)
    monkeypatch.setattr(settings, "rerank_max_candidates", 10)
    docs = [Document(page_content=f"doc {i}") for i in range(15)]

    top = reranker.rerank("q", docs, 4)

    assert len(fake.pairs) == 10
    assert [d.page_content for d in top] == ["doc 0", "doc 1", "doc 2", "doc 3"]
    assert "_rerank_score" not in docs[12].metadata
