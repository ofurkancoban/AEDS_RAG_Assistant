"""Cross-process invalidation of the per-worker BM25 index.

The index itself is not built here (that needs Chroma and the corpus). What is
under test is the signal that tells a worker its cached index is stale, which
is the part that was missing: clearing a dict only ever reached one process.
"""

from db import chroma_client
from db.models import CorpusVersion, SessionLocal


def test_the_counter_starts_at_zero_and_advances():
    assert chroma_client.corpus_version() == 0
    assert chroma_client.bump_corpus_version() == 1
    assert chroma_client.bump_corpus_version() == 2
    assert chroma_client.corpus_version() == 2


def test_the_counter_is_a_single_shared_row():
    chroma_client.bump_corpus_version()
    chroma_client.bump_corpus_version()

    session = SessionLocal()
    try:
        rows = session.query(CorpusVersion).all()
        # One row, updated in place. A row per bump would make "has anything
        # changed since I built my index" a scan instead of a lookup.
        assert len(rows) == 1 and rows[0].id == 1
    finally:
        session.close()


def test_a_stale_worker_drops_its_cache_on_the_next_search(monkeypatch):
    """What a second uvicorn worker experiences.

    This worker's cache was built at the version before another process
    changed the corpus, so the next search must rebuild rather than answer
    from a keyword index that no longer matches the approved chunks.
    """
    built = []

    class FakeCollection:
        def get(self, where, include):
            built.append(dict(where))
            return {"documents": ["a chunk of text"], "metadatas": [{"source_id": "x"}]}

    monkeypatch.setattr(
        chroma_client, "get_vector_store", lambda: type("S", (), {"_collection": FakeCollection()})()
    )
    monkeypatch.setattr(chroma_client, "_bm25_cache", {})
    monkeypatch.setattr(chroma_client, "_bm25_cache_version", None)

    chroma_client._build_bm25_retriever(None)
    assert len(built) == 1

    # Same version: the cached index is still valid, no rebuild.
    chroma_client._build_bm25_retriever(None)
    assert len(built) == 1

    # Another process changed the corpus.
    chroma_client.bump_corpus_version()

    chroma_client._build_bm25_retriever(None)
    assert len(built) == 2, "a corpus change in another process was not noticed"


def test_invalidating_locally_also_advances_the_shared_counter(monkeypatch):
    # invalidate_all touches cached_answers, which is not what this asserts.
    monkeypatch.setattr("db.semantic_cache.invalidate_all", lambda: 0)

    before = chroma_client.corpus_version()
    chroma_client._invalidate_bm25_cache()

    # Without the bump, the acting worker would clear its own cache and leave
    # every other worker unaware anything had changed.
    assert chroma_client.corpus_version() == before + 1
