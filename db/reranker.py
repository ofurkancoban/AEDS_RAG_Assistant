
import threading
from functools import lru_cache

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


_CLOUDFLARE_RERANK_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/baai/bge-reranker-base"
# After a failed API call the local model is used for this long, so an
# outage costs one timeout rather than one per question.
# One slow call (the API's median is about 0.5s, but single calls over 3s
# happen) used to move every question to the local model for five minutes:
# about 3s slower on the VPS, and ranked differently. A timeout is now
# retried once, and the pause after a real failure is one minute.
_API_BACKOFF_S = 60
_API_ATTEMPTS = 2
_api_down_until = 0.0
# The same pause in wall-clock time, with why, for the admin status card.
_api_down_state: dict = {"until": 0.0, "reason": None}


def _seconds_to_utc_midnight() -> float:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - now).total_seconds()


def _allocation_used_up(exc: Exception) -> bool:
    """The account's free daily allocation (10,000 neurons) is spent. Every
    call fails until it resets at 00:00 UTC, so retrying each minute only
    adds a wasted request to every question."""
    import httpx

    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 429:
        return False
    body = exc.response.text
    return "4006" in body or "daily free allocation" in body


def hosted_status() -> dict:
    """For the admin panel: whether the hosted reranker is in use, or until
    when (Unix time) the local model stands in, and why."""
    import time

    if not _api_configured():
        return {"state": "local_only", "until": None, "reason": None}
    if time.monotonic() < _api_down_until and _api_down_state["until"] > time.time():
        return {"state": "paused", "until": _api_down_state["until"], "reason": _api_down_state["reason"]}
    return {"state": "hosted", "until": None, "reason": None}


def _api_configured() -> bool:
    return bool(settings.cloudflare_account_id and settings.cloudflare_api_token)


def _api_scores(query: str, passages: list[str]) -> list[float] | None:
    """Scores from the hosted model, in passage order, or None to fall back
    to the local one."""
    global _api_down_until
    import time

    import httpx

    if not _api_configured() or time.monotonic() < _api_down_until:
        return None
    for attempt in range(1, _API_ATTEMPTS + 1):
        try:
            response = httpx.post(
                _CLOUDFLARE_RERANK_URL.format(account=settings.cloudflare_account_id),
                headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"},
                json={"query": query, "contexts": [{"text": p} for p in passages], "top_k": len(passages)},
                timeout=settings.reranker_api_timeout_s,
            )
            response.raise_for_status()
            scores = [0.0] * len(passages)
            ranked = response.json()["result"]["response"]
            for item in ranked:
                scores[item["id"]] = float(item["score"])
            if len(ranked) != len(passages):
                raise ValueError(f"{len(ranked)} scores for {len(passages)} passages")
            return scores
        except httpx.TimeoutException as exc:
            if attempt < _API_ATTEMPTS:
                continue
            failure = exc
        except Exception as exc:  # noqa: BLE001 - any failure means: use the local model
            failure = exc
        break
    import logging

    used_up = _allocation_used_up(failure)
    if used_up:
        pause = _seconds_to_utc_midnight()
        logging.getLogger(__name__).warning(
            "Hosted reranker: daily free allocation used up, using the local model for %.0f minutes", pause / 60
        )
        import ops_alerts

        ops_alerts.alert_once_per_day(
            "cloudflare_allocation",
            "Cloudflare Workers AI: the free daily allocation (10,000 neurons) is used up. "
            f"The reranker uses the local model (about 3s slower) for {pause / 3600:.1f} hours, "
            "until 00:00 UTC, and the Workers AI answer fallback is unavailable until then.",
        )
    else:
        pause = _API_BACKOFF_S
        logging.getLogger(__name__).warning("Hosted reranker failed, using the local model: %s", failure)
    _api_down_until = time.monotonic() + pause
    _api_down_state.update(until=time.time() + pause, reason="allocation" if used_up else "error")
    return None


@lru_cache(maxsize=256)
def _markdown_title(source_file: str) -> str:
    """A Markdown document's own top heading ("# Broadcast fee
    (Rundfunkbeitrag) for students in Germany"), or "" when there is none."""
    path = settings.documents_dir / source_file
    if path.suffix.lower() != ".md" or not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _rerank_text(doc: Document) -> str:
    """What the reranker reads for a passage: Markdown sections are stored
    without their document's title, so "## How much - 18.36 euros per month"
    could not be matched to a question about the Rundfunkbeitrag and fell
    out of the top passages (2026-10-15). The title is added for scoring
    only; the stored passage and what the model sees are unchanged.
    PDF chunks already start with their own "[title | section]" header."""
    title = _markdown_title(doc.metadata.get("source_file") or "")
    if title and not doc.page_content.lstrip().startswith(("# " + title, title)):
        # After the passage, not before: measured on four questions, a title
        # in front pushed a section with the answer down ("Levels, length
        # and credits" from 3rd to 4th-5th), while at the end it lifted the
        # Rundfunkbeitrag answer from 5th to 1st and moved nothing down.
        return f"{doc.page_content}\n({title})"
    return doc.page_content


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

    texts = [_rerank_text(doc) for doc in docs]
    scores = _api_scores(query, texts)
    if scores is None:
        pairs = [(query, text) for text in texts]
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
