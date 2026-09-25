import time

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from concurrency import once
from config import settings

COLLECTION_NAME = "approved_chunks"


class _RetryingEmbeddings(Embeddings):
    """Wraps another Embeddings implementation with retry-with-backoff on
    rate-limit errors. Unlike langchain_google_genai's chat model (which
    retries via tenacity internally), GoogleGenerativeAIEmbeddings.
    embed_documents raises immediately on any error - so a burst of chunks
    during a bulk re-ingest can trip the free tier's per-minute quota
    (100 requests/min) and crash the whole ingestion instead of just waiting
    a few seconds and continuing."""

    def __init__(self, inner: Embeddings, max_attempts: int = 8, initial_delay: float = 65.0):
        self._inner = inner
        self._max_attempts = max_attempts
        # The free tier's embedding quota is per-minute (100 requests/min), so
        # a retry sooner than ~a minute just collides with the same still-open
        # window instead of actually waiting it out - hence starting at 65s
        # rather than a short exponential ramp.
        self._initial_delay = initial_delay

    def _call_with_retry(self, fn, *args, **kwargs):
        delay = self._initial_delay
        for attempt in range(self._max_attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "quota" in str(exc).lower() or "ResourceExhausted" in type(exc).__name__
                if not is_rate_limit or attempt == self._max_attempts - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 1.5, 120)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # A smaller outgoing batch (vs. the library's own default of 100)
        # means one large document's own embed_documents call is less likely
        # to need several sub-batch requests back-to-back and trip the
        # per-minute quota on its own.
        batch_size = 20
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            all_embeddings.extend(self._call_with_retry(self._inner.embed_documents, batch))
        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        return self._call_with_retry(self._inner.embed_query, text)


_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class _LocalEmbeddings(Embeddings):
    """Wraps a local sentence-transformers model as a langchain Embeddings
    implementation - runs entirely on-device (CPU/MPS/CUDA, auto-detected via
    db.reranker's device selection), no API calls, no rate limit, no
    per-query cost."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        from db.reranker import _select_device

        self._model = SentenceTransformer(model_name, device=_select_device())
        # BGE's own model card recommends prefixing queries (but not
        # documents/passages) with this instruction for retrieval tasks -
        # improves asymmetric query-to-passage matching quality.
        self._query_instruction = _BGE_QUERY_INSTRUCTION if "bge" in model_name.lower() else ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            [self._query_instruction + text], convert_to_numpy=True, normalize_embeddings=True
        )
        return vector[0].tolist()


@once
def get_embeddings() -> Embeddings:
    if settings.embedding_provider == "local":
        return _LocalEmbeddings(settings.local_embedding_model)

    if settings.embedding_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return _RetryingEmbeddings(
            GoogleGenerativeAIEmbeddings(
                model=settings.gemini_embedding_model,
                google_api_key=settings.gemini_api_key,
            )
        )

    return OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    )


@once
def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(settings.chroma_persist_dir),
    )


def add_chunks(texts: list[str], metadatas: list[dict], ids: list[str]) -> None:
    """Write chunks to Chroma. Callers must ensure metadata['status'] == 'approved'
    before calling this - unapproved content must never reach the vector store."""
    store = get_vector_store()
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    _invalidate_bm25_cache()


def delete_chunks_by_source_id(source_id: str) -> None:
    """Remove all chunks for a source_id. Used before re-ingesting a changed file
    so its old chunks don't linger alongside the freshly embedded ones."""
    store = get_vector_store()
    result = store._collection.get(where={"source_id": source_id}, include=[])
    ids = result["ids"]
    if ids:
        store._collection.delete(ids=ids)
    _invalidate_bm25_cache()


def delete_chunks_by_submission_id(submission_id: int) -> int:
    """Remove the chunk(s) a given approved submission produced, returning how
    many were deleted.

    Keyed on the submission_id that ingest_approved_submission writes into
    every chunk's metadata rather than on a stored chunk id, so revoking works
    for submissions approved before that link was tracked anywhere.
    """
    store = get_vector_store()
    ids = store._collection.get(where={"submission_id": submission_id}, include=[])["ids"]
    if ids:
        store._collection.delete(ids=ids)
        _invalidate_bm25_cache()
    return len(ids)


def _set_chunk_status(chunk_id: str, status: str) -> bool:
    store = get_vector_store()
    existing = store._collection.get(ids=[chunk_id], include=["metadatas"])
    metadatas = existing.get("metadatas") or []
    if not metadatas:
        return False
    store._collection.update(ids=[chunk_id], metadatas=[{**metadatas[0], "status": status}])
    _invalidate_bm25_cache()
    return True


def mark_deprecated(chunk_id: str) -> None:
    """Hide a chunk from retrieval without deleting it - every search filters on
    status == "approved" - so an approved correction supersedes the original."""
    _set_chunk_status(chunk_id, "deprecated")


def restore_chunk(chunk_id: str) -> bool:
    """Undo mark_deprecated. Needed when revoking an approved correction: the
    correction's own chunk goes away, so leaving the original it superseded
    hidden would silently delete that content from the corpus instead of
    returning it to the state it was in before the approval."""
    return _set_chunk_status(chunk_id, "approved")


def _where(filter: dict | None) -> dict:
    """Build Chroma's metadata filter, always scoped to approved chunks.

    Chroma rejects a plain mapping with more than one key ("Expected where to
    have exactly one operator"), so any additional condition has to be wrapped
    in $and. Passing {"status": ..., "source_id": ...} raised a ValueError,
    which meant every request carrying a source_id_filter failed with a 500.
    The UI never sends one, so this went unnoticed - but the field is part of
    the public request body and anyone can set it.
    """
    # "approved" is applied last so a caller-supplied filter cannot widen the
    # scope by setting its own status. Today the only filter the request path
    # can influence is source_id, but the invariant is worth enforcing here
    # rather than depending on every future caller to respect it.
    conditions = {**(filter or {}), "status": "approved"}
    if len(conditions) == 1:
        return conditions
    return {"$and": [{key: value} for key, value in conditions.items()]}


def similarity_search(query: str, k: int, filter: dict | None = None):
    store = get_vector_store()
    return store.similarity_search(query, k=k, filter=_where(filter))


# Keyed by the sorted (key, value) pairs of the effective "where" filter, so
# distinct filter combinations (e.g. a source_id-scoped search) get their own
# cached index. Rebuilding a BM25 index means pulling every approved chunk out
# of Chroma and re-tokenizing it - cheap once, but a real cost to repeat on
# every single query as the corpus grows. Invalidated (cleared entirely, not
# per-key - simplest correct option) whenever the approved-chunk set changes:
# see _invalidate_bm25_cache, called from add_chunks/delete_chunks_by_source_id
# /mark_deprecated, and _build_bm25_retriever for how a change made in another
# process reaches this one.
_bm25_cache: dict[tuple, BM25Retriever | None] = {}

# The corpus version this process built its cached indexes at. Clearing the
# dict above only reaches THIS process; a second uvicorn worker would go on
# answering from a keyword index built before the corpus changed, so an
# approved correction would be visible or not depending on which worker took
# the request. The shared counter (db.models.CorpusVersion) is what lets every
# worker notice a change made by any of them.
_bm25_cache_version: int | None = None


def corpus_version() -> int:
    """Current value of the shared corpus counter."""
    from db.models import CorpusVersion, SessionLocal

    session = SessionLocal()
    try:
        row = session.get(CorpusVersion, 1)
        return row.version if row else 0
    finally:
        session.close()


def bump_corpus_version() -> int:
    """Record that the approved-chunk set changed. Returns the new value."""
    from db.models import CorpusVersion, SessionLocal

    session = SessionLocal()
    try:
        row = session.get(CorpusVersion, 1)
        if row is None:
            row = CorpusVersion(id=1, version=1)
            session.add(row)
        else:
            row.version += 1
        session.commit()
        return row.version
    finally:
        session.close()


def _invalidate_bm25_cache() -> None:
    global _bm25_cache_version

    _bm25_cache.clear()
    _bm25_cache_version = bump_corpus_version()
    # Cached answers are derived from the approved-chunk set too, so anything
    # that changes that set has to drop them as well - otherwise an approved
    # correction silently fails to reach users who ask the cached question.
    # Imported lazily: db.semantic_cache imports db.models, which imports
    # config, and a module-level import here would create a cycle.
    from db.semantic_cache import invalidate_all

    invalidate_all()


def _build_bm25_retriever(filter: dict | None) -> BM25Retriever | None:
    global _bm25_cache_version

    # One small indexed read per search, against an LLM call that costs
    # seconds. Cheap enough that checking every time is preferable to a
    # staleness window nobody would remember exists.
    current = corpus_version()
    if _bm25_cache_version != current:
        _bm25_cache.clear()
        _bm25_cache_version = current

    # Cache key from the plain conditions, query from the $and form Chroma
    # needs - a nested dict would not be hashable as a key anyway.
    conditions = {"status": "approved", **(filter or {})}
    where = _where(filter)
    cache_key = tuple(sorted(conditions.items()))
    if cache_key in _bm25_cache:
        return _bm25_cache[cache_key]

    store = get_vector_store()
    result = store._collection.get(where=where, include=["documents", "metadatas"])
    texts = result.get("documents") or []
    retriever = BM25Retriever.from_texts(texts, metadatas=result["metadatas"]) if texts else None
    _bm25_cache[cache_key] = retriever
    return retriever


_RRF_CONSTANT = 60


def hybrid_search(query: str, k: int, filter: dict | None = None) -> list[Document]:
    """Combine embedding similarity with BM25 keyword matching via Reciprocal
    Rank Fusion: each doc's final score is the sum of 1/(constant + rank) across
    whichever of the two rankings it appears in, then the union is re-sorted by
    that combined score. This (rather than e.g. taking vector hits first and
    only appending BM25 leftovers until some budget runs out) is what actually
    lets a lower-ranked-by-embedding but exact-keyword-matched BM25 hit (a
    module code, an ECTS figure) outrank a mediocre vector match instead of
    being crowded out by whatever the vector search happened to return first."""
    vector_docs = similarity_search(query, k=k, filter=filter)

    bm25_retriever = _build_bm25_retriever(filter)
    if bm25_retriever is None:
        return vector_docs
    bm25_retriever.k = max(k * 3, 20)
    bm25_docs = bm25_retriever.invoke(query)

    def dedup_key(doc: Document) -> tuple:
        return (doc.metadata.get("source_id"), doc.page_content)

    scores: dict[tuple, float] = {}
    doc_by_key: dict[tuple, Document] = {}

    for rank, doc in enumerate(vector_docs, start=1):
        key = dedup_key(doc)
        scores[key] = scores.get(key, 0.0) + 1 / (_RRF_CONSTANT + rank)
        doc_by_key[key] = doc

    for rank, doc in enumerate(bm25_docs, start=1):
        key = dedup_key(doc)
        scores[key] = scores.get(key, 0.0) + 1 / (_RRF_CONSTANT + rank)
        doc_by_key.setdefault(key, doc)

    ranked_keys = sorted(scores, key=lambda key: scores[key], reverse=True)
    final_k = k + max(2, k // 2)
    result = [doc_by_key[key] for key in ranked_keys[:final_k]]
    # Stashed for the Vector Analytics view (see db/reranker.py's matching
    # _rerank_score annotation) - not written back to Chroma.
    for key, doc in zip(ranked_keys[:final_k], result):
        doc.metadata["_hybrid_score"] = scores[key]
    return result


@once
def get_embedding_dimension() -> int:
    """Probes the configured embedding model once and caches the result - the
    dimension is a fixed property of whichever model settings.embedding_provider
    selects, so there's no need to re-embed a probe string on every
    /admin/stats call."""
    return len(get_embeddings().embed_query("dimension probe"))


def get_corpus_stats() -> dict:
    """Real corpus-wide counts for the Vector Analytics view - total approved
    chunks and distinct source documents - as opposed to the prototype's
    client-held chunk array, which only ever reflected whatever happened to
    still be in one browser tab's React state."""
    store = get_vector_store()
    result = store._collection.get(where={"status": "approved"}, include=["metadatas"])
    metadatas = result.get("metadatas") or []
    source_ids = {meta.get("source_id") for meta in metadatas if meta.get("source_id")}
    return {
        "total_chunks": len(metadatas),
        "total_sources": len(source_ids),
    }


def get_filterable_fields(sample_values_per_field: int = 8) -> dict[str, list[str]]:
    """Scan approved chunks for 'field_*' metadata (attached to structured rows
    from CSV/XLSX sources, see ingestion/loaders.py) and collect a sample of
    distinct values per field. Used to ground the enumeration-query classifier
    in fields/values that actually exist in this dataset, instead of it having
    to guess plausible-sounding ones."""
    store = get_vector_store()
    result = store._collection.get(where={"status": "approved"}, include=["metadatas"])
    fields: dict[str, set] = {}
    for meta in result["metadatas"]:
        for key, value in meta.items():
            if key.startswith("field_"):
                fields.setdefault(key, set()).add(str(value))
    return {key: sorted(values)[:sample_values_per_field] for key, values in fields.items()}


def get_all_field_values(field: str) -> list[str]:
    """Every distinct value seen for a field_* metadata key, uncapped (unlike
    get_filterable_fields' small grounding sample) - used to match a name
    extracted from a question (e.g. 'Who is Oliver Kramer?') against the full
    set of professors, not just whichever handful happen to sort first."""
    store = get_vector_store()
    result = store._collection.get(where={"status": "approved"}, include=["metadatas"])
    values = {str(meta[field]) for meta in result["metadatas"] if field in meta}
    return sorted(values)


def get_all_rows_for_source(source_id: str, limit: int = 200) -> list[Document]:
    """Every chunk for a given source_id, unranked - used for 'what's the full
    curriculum' style questions where the goal is the entire clean structured
    dataset (e.g. the course catalog), not a similarity-ranked top-k that can
    pull in unrelated prose from a different document (or, in a multi-programme
    module handbook, a different degree programme's modules) alongside it."""
    store = get_vector_store()
    result = store._collection.get(
        where={"$and": [{"status": "approved"}, {"source_id": source_id}]},
        include=["documents", "metadatas"],
        limit=limit,
    )
    return [
        Document(page_content=doc, metadata=meta)
        for doc, meta in zip(result["documents"], result["metadatas"])
    ]


def filter_search(field: str, value: str, limit: int = 50) -> list[Document]:
    """Direct metadata-equality fetch, not similarity-ranked - for enumeration
    questions ('list all compulsory courses') where the goal is every matching
    record, which top-k similarity/keyword ranking isn't built to guarantee."""
    store = get_vector_store()
    result = store._collection.get(
        where={"$and": [{"status": "approved"}, {field: value}]},
        include=["documents", "metadatas"],
        limit=limit,
    )
    return [
        Document(page_content=doc, metadata=meta)
        for doc, meta in zip(result["documents"], result["metadatas"])
    ]
