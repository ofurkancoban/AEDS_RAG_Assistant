
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


@once
def get_reranker() -> CrossEncoder:
    # Loaded once and kept resident (like the Ollama models via keep_alive) -
    # this is a ~560M param cross-encoder, reloading it per request would add
    # several seconds of latency to every query.
    return CrossEncoder(settings.reranker_model, device=_select_device())


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

    pairs = [(query, doc.page_content) for doc in docs]
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
