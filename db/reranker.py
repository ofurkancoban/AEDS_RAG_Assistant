
import threading

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from concurrency import once
from config import settings


def _select_device() -> str:
    """Prefers Apple Silicon's MPS backend, then CUDA, falling back to CPU -
    a real GPU/MPS backend meaningfully speeds up this per-request inference
    over plain CPU, and both are auto-detected here since a CPU-only
    deployment target (e.g. the VPS this project can also run on) simply
    won't have either available."""
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


# One forward pass at a time through each resident model (this cross-encoder
# and the local embedding model in db/chroma_client.py). Speculative
# retrieval runs searches on several pool threads; concurrent passes through
# one model on MPS were seen to spin forever in transformers' mask setup
# (three threads, no progress for 28 minutes). Each pass takes milliseconds,
# so serialising them costs next to nothing.
MODEL_LOCK = threading.Lock()


@once
def get_reranker() -> CrossEncoder:
    # Loaded once and kept resident (like the Ollama models via keep_alive) -
    # this is a ~560M param cross-encoder, reloading it per request would add
    # several seconds of latency to every query.
    kwargs = {"max_length": settings.reranker_max_length} if settings.reranker_max_length > 0 else {}
    return CrossEncoder(settings.reranker_model, device=_select_device(), **kwargs)


def rerank(query: str, docs: list[Document], top_k: int) -> list[Document]:
    """Re-scores a candidate pool for actual relevance to the query via a
    cross-encoder (which jointly encodes query+document, unlike the
    embedding/BM25 union that scored each candidate independently), then
    returns only the top_k - this is what lets a fine-grained distinction
    (the one exam rule or ECTS figure that actually answers the question,
    among several similar-looking chunks) win out over the merely
    topically-similar candidates that hybrid_search's pool still contains."""
    if not docs:
        return docs
    if settings.rerank_max_candidates > 0:
        # hybrid_search returns its pool best-first (fused rank), so the cut
        # keeps its strongest candidates; see config.rerank_max_candidates.
        docs = docs[: settings.rerank_max_candidates]

    pairs = [(query, doc.page_content) for doc in docs]
    with MODEL_LOCK:
        scores = get_reranker().predict(pairs)

    # Stashed on metadata (not written back to Chroma - these Document objects
    # are transient, freshly read copies) so the Vector Analytics view can show
    # the real cross-encoder score behind each answer instead of a fake one.
    for score, doc in zip(scores, docs):
        doc.metadata["_rerank_score"] = float(score)

    if len(docs) <= top_k:
        return docs

    ranked = sorted(zip(scores, docs), key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in ranked[:top_k]]
