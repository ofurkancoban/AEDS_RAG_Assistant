"""Numbered passage citations ([1], [2]...) and live progress stages.

The web UI turns "[n]" in an answer into a clickable citation pointing at
retrieval[n-1], and shows a step list while an answer is being produced from
'stage' events. These cover the backend half of both."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from api.telegram_chat import _format_reply
from graph import progress
from graph.build_graph import _with_latency_logging
from graph.nodes import _normalize_passage_markers, strip_passage_markers


def test_markers_within_range_are_kept():
    assert _normalize_passage_markers("Deadline is **15 March** [1].", 4) == "Deadline is **15 March** [1]."


def test_comma_lists_are_split_into_separate_markers():
    assert _normalize_passage_markers("Two retakes [1, 3] allowed.", 4) == "Two retakes [1][3] allowed."


def test_markers_with_no_matching_passage_are_dropped():
    # A citation the reader can click must lead somewhere real.
    assert _normalize_passage_markers("Invented [7] here.", 4) == "Invented here."
    assert _normalize_passage_markers("Mixed [2][9] ok.", 4) == "Mixed [2] ok."


def test_no_passages_means_no_markers():
    # Structured-lookup answers (course catalog, deadlines table) have no
    # retrieved passages, so nothing they cite can be resolved.
    assert _normalize_passage_markers("Prof. X teaches it [1].", 0) == "Prof. X teaches it."


def test_markdown_links_and_indentation_survive():
    assert _normalize_passage_markers("A [link](http://x) stays [2].", 4) == "A [link](http://x) stays [2]."
    nested = "- a\n  - nested [1]  \nnext"
    assert _normalize_passage_markers(nested, 4) == nested


def test_strip_passage_markers_removes_every_marker():
    assert strip_passage_markers("Deadline is 15 March [1][2]. Ok [3].") == "Deadline is 15 March. Ok."


def test_telegram_reply_never_shows_citation_numbers():
    reply = _format_reply("You may retake an exam **twice** [1][2].", [{"source_id": "exam_regs"}])
    assert "[1]" not in reply and "[2]" not in reply
    assert "twice" in reply


def test_report_stage_is_a_no_op_without_a_listener():
    progress.report_stage(progress.SEARCHING)  # must not raise


class _State(TypedDict, total=False):
    value: int
    node_latencies: dict


def test_node_wrapper_forwards_stages_through_a_real_graph_run():
    # Regression guard: LangGraph only passes `config` to a node whose
    # signature declares it, and inspect.signature follows functools.wraps'
    # __wrapped__ - a wraps()-decorated wrapper would silently never receive
    # the reporter and the UI would sit on its first step forever.
    def node(state):
        progress.report_stage(progress.UNDERSTANDING)
        progress.report_stage(progress.WRITING)
        return {"value": 1}

    builder = StateGraph(_State)
    builder.add_node("only", _with_latency_logging("only", node))
    builder.add_edge(START, "only")
    builder.add_edge("only", END)
    graph = builder.compile()

    seen: list[str] = []
    result = graph.invoke({"value": 0}, config={"configurable": {"report_stage": seen.append}})

    assert seen == [progress.UNDERSTANDING, progress.WRITING]
    assert result["value"] == 1
    assert "only" in result["node_latencies"]


def test_node_wrapper_works_without_a_reporter():
    def node(state):
        progress.report_stage(progress.SEARCHING)
        return {"value": 2}

    builder = StateGraph(_State)
    builder.add_node("only", _with_latency_logging("only", node))
    builder.add_edge(START, "only")
    builder.add_edge("only", END)

    assert builder.compile().invoke({"value": 0})["value"] == 2
