import functools
import logging
import time
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from concurrency import once
from config import settings
from graph.nodes import detect_contribution_node, generate_node, retrieve_node
from graph.state import RagState

logger = logging.getLogger(__name__)


def _with_latency_logging(node_name: str, fn):
    """Wraps a graph node to log its execution time - cheap, dependency-free
    observability (no LangSmith/Phoenix account or OpenTelemetry collector
    needed) that's enough to answer "which node is slow" from the existing
    log stream."""

    @functools.wraps(fn)
    def wrapper(state):
        start = time.monotonic()
        result = fn(state)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("node=%s latency_ms=%.0f", node_name, elapsed_ms)
        # Also surfaced in the API response (see run_chat/stream_chat) for the
        # Vector Analytics view's "Last Query Latency" breakdown - a real
        # per-node timing instead of the prototype's single fabricated number.
        result = dict(result)
        result["node_latencies"] = {**state.get("node_latencies", {}), node_name: round(elapsed_ms, 1)}
        return result

    return wrapper


@once
def get_compiled_graph():
    import sqlite3

    conn = sqlite3.connect(str(settings.checkpointer_sqlite_path), check_same_thread=False)
    # WAL mode lets readers and a writer proceed concurrently instead of
    # blocking on a single exclusive lock - without it, concurrent chat
    # requests hitting the checkpointer at the same time risk "database is
    # locked" errors under load.
    conn.execute("PRAGMA journal_mode=WAL")
    checkpointer = SqliteSaver(conn)

    builder = StateGraph(RagState)
    builder.add_node("retrieve", _with_latency_logging("retrieve", retrieve_node))
    builder.add_node("generate", _with_latency_logging("generate", generate_node))
    builder.add_node("detect_contribution", _with_latency_logging("detect_contribution", detect_contribution_node))
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", "detect_contribution")
    builder.add_edge("detect_contribution", END)

    return builder.compile(checkpointer=checkpointer)


def _build_sources(retrieved_docs: list) -> list[dict]:
    # Previously a source past its valid_until (see db/freshness.py) was only
    # ever flagged in the LLM's own prose - if the model dropped that caveat
    # (paraphrasing it away, or just not following the instruction), the chat
    # UI showed a stale date with no visible warning at all. This puts the
    # same fact directly on the source entry itself, so the UI can render it
    # regardless of what the model actually wrote.
    from db.freshness import get_expired_source_ids

    expired = get_expired_source_ids()

    sources = [
        {
            "source_id": doc.metadata.get("source_id", "unknown"),
            "page": doc.metadata.get("page"),
            "url": doc.metadata.get("source_url"),
            # isoformat string, not a date: this dict is also json.dumps'd
            # verbatim into CachedAnswer.sources_json (see db/semantic_cache.py).
            "expired_since": (
                expiry.isoformat()
                if (expiry := expired.get(doc.metadata.get("source_id", "")))
                else None
            ),
        }
        for doc in retrieved_docs
    ]
    # de-duplicate while preserving order
    seen = set()
    unique_sources = []
    for source in sources:
        key = (source["source_id"], source["page"])
        if key not in seen:
            seen.add(key)
            unique_sources.append(source)
    return unique_sources


def _build_retrieval_diagnostics(retrieved_docs: list) -> list[dict]:
    """Per-chunk hybrid/rerank scores (see db/chroma_client.py's _hybrid_score
    and db/reranker.py's _rerank_score metadata annotations) - real retrieval
    diagnostics for the Vector Analytics view, not the client-held cosine
    similarity the original prototype fabricated from in-browser embeddings.

    Also carries expired_since (see _build_sources) - this is the list the
    chat UI's "Verified Document Passages Used" panel actually renders, so
    that is where a stale-source badge needs the data, not just the
    deduplicated `sources` list.
    """
    from db.freshness import get_expired_source_ids

    expired = get_expired_source_ids()

    return [
        {
            "source_id": doc.metadata.get("source_id", "unknown"),
            "snippet": doc.page_content[:200],
            "hybrid_score": doc.metadata.get("_hybrid_score"),
            "rerank_score": doc.metadata.get("_rerank_score"),
            "expired_since": (
                expiry.isoformat()
                if (expiry := expired.get(doc.metadata.get("source_id", "")))
                else None
            ),
        }
        for doc in retrieved_docs
    ]


_UNANSWERED_MARKERS = (
    "do not contain",
    "does not contain",
    "not contain any information",
    "no information about",
    "not mentioned in",
    "not specified in",
    "not covered",
    "unable to answer",
    "i don't have",
    "i do not have",
)


def _has_passed_deadline(answer: str) -> bool:
    """True when the answer states that an application deadline has already
    passed (see ingestion/deadlines.py's DEADLINE_PASSED_MARKER, appended by
    _route_with_tools's lookup_application_deadline handling). This bypasses
    retrieval entirely (see time_sensitive's own docstring), so it carries no
    retrieved_docs for _build_sources/_build_retrieval_diagnostics' expiry
    labelling to attach to - the chat UI needs this separate signal to show
    the same "this describes a closed cycle" warning on an answer that has no
    sources at all."""
    from ingestion.deadlines import DEADLINE_PASSED_MARKER

    return DEADLINE_PASSED_MARKER in answer


def _looks_unanswered(answer: str) -> bool:
    """Heuristic 'the corpus could not answer this' detector, used only to
    label query_log rows - never to alter the answer itself. Its whole purpose
    is to surface content gaps in the admin analytics view: the questions
    users ask that the documents cannot currently answer are the most direct
    evidence of what is missing from the corpus."""
    lowered = answer.casefold()
    return any(marker in lowered for marker in _UNANSWERED_MARKERS)


def is_cacheable_turn(thread_id: str) -> bool:
    """True only for the first question in a thread.

    A mid-conversation question can depend on earlier turns (generate_node is
    given a sliding window of them, and short follow-ups like 'yes, list them'
    are explicitly resolved against the previous turn), so an answer produced
    in one thread's context must not be replayed into another thread that
    merely asked something similar-looking.
    """
    graph = get_compiled_graph()
    state = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    return not state.get("messages")


def run_chat(thread_id: str, question: str, source_id_filter: str | None = None) -> dict:
    from langchain_core.messages import HumanMessage

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "source_id_filter": source_id_filter,
        },
        config=config,
    )

    answer = result["messages"][-1].content
    return {
        "answer": answer,
        "sources": _build_sources(result.get("retrieved_docs", [])),
        "detected_contribution": result.get("detected_contribution"),
        "retrieval": _build_retrieval_diagnostics(result.get("retrieved_docs", [])),
        "node_latencies": result.get("node_latencies", {}),
        "answered": not _looks_unanswered(answer),
        "time_sensitive": bool(result.get("time_sensitive")),
        "has_expired_deadline": _has_passed_deadline(answer),
    }


def stream_chat(
    thread_id: str, question: str, source_id_filter: str | None = None
) -> Iterator[tuple[str, dict]]:
    """Yields ('token', {'text': str}) as the answer is generated, followed by
    exactly one final ('done', {'sources': [...], 'detected_contribution': ...})
    once the graph run completes. Only tokens from the 'generate' node are
    streamed - the classifier nodes' raw JSON output is never shown to the
    user."""
    from langchain_core.messages import HumanMessage

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}

    for message_chunk, metadata in graph.stream(
        {
            "messages": [HumanMessage(content=question)],
            "source_id_filter": source_id_filter,
        },
        config=config,
        stream_mode="messages",
    ):
        if metadata.get("langgraph_node") == "generate" and message_chunk.content:
            yield ("token", {"text": message_chunk.content})

    final_state = graph.get_state(config).values
    final_answer = final_state["messages"][-1].content
    yield (
        "done",
        {
            "sources": _build_sources(final_state.get("retrieved_docs", [])),
            "detected_contribution": final_state.get("detected_contribution"),
            # the generate node may have cleaned up the raw streamed tokens
            # (stripped thinking tags, fabricated citations, etc) - this is the
            # authoritative final text, which can differ from the concatenation
            # of the 'token' events the client already displayed
            "final_answer": final_answer,
            "retrieval": _build_retrieval_diagnostics(final_state.get("retrieved_docs", [])),
            "node_latencies": final_state.get("node_latencies", {}),
            "answered": not _looks_unanswered(final_answer),
            "time_sensitive": bool(final_state.get("time_sensitive")),
            "has_expired_deadline": _has_passed_deadline(final_answer),
        },
    )
