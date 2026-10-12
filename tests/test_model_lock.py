import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from langchain_core.documents import Document

from db import chroma_client, reranker


class _Recorder:
    """Stands in for both models and records how many calls overlap."""

    def __init__(self):
        self.active = 0
        self.peak = 0
        self._guard = threading.Lock()

    def _enter(self):
        with self._guard:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.02)
        with self._guard:
            self.active -= 1

    def encode(self, texts, **kw):
        self._enter()
        return np.zeros((len(texts), 3))

    def predict(self, pairs):
        self._enter()
        return [0.5] * len(pairs)


def test_embedding_and_rerank_passes_never_overlap(monkeypatch):
    model = _Recorder()
    embeddings = chroma_client._LocalEmbeddings.__new__(chroma_client._LocalEmbeddings)
    embeddings._model = model
    embeddings._query_instruction = ""
    monkeypatch.setattr(reranker, "get_reranker", lambda: model)
    docs = [Document(page_content="x", metadata={})]

    def work(i):
        if i % 2:
            embeddings.embed_query("q")
        else:
            reranker.rerank("q", docs, 1)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, range(12)))

    assert model.peak == 1
