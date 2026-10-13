"""Stopping a streamed answer stops the LLM.

The graph runs in its own thread (see graph/build_graph.py's stream_chat), so
before this, a reader pressing Stop or closing the tab only stopped the
events from being sent: the model kept generating the whole answer, on
quota, for nobody. These tests run a real LangGraph graph around a slow fake
chat model wired like generate_node's (a fallback model behind it, and a
retry loop that catches Exception like _with_resilience), and check that
closing the stream ends generation within a token or two, without a retry
or a call to the fallback model."""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import TypedDict

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from graph import build_graph

WORDS = 200
ANSWER = " ".join(f"w{i}" for i in range(WORDS))


# Module-level on purpose: pydantic copies a dict or list passed to the model.
CALLS: dict = {}
PRODUCED: list = []


class _Model(GenericFakeChatModel):
    label: str = "primary"

    def _stream(self, *args, **kwargs):
        CALLS[self.label] += 1
        for chunk in super()._stream(*args, **kwargs):
            PRODUCED.append(chunk)
            time.sleep(0.01)
            yield chunk


@pytest.fixture
def slow_graph(monkeypatch):
    """Patches in a one-node graph whose 'generate' node streams ANSWER slowly."""
    CALLS.clear()
    CALLS.update(primary=0, fallback=0, retries=0)
    PRODUCED.clear()
    calls, produced = CALLS, PRODUCED

    def model(label):
        return _Model(messages=iter([AIMessage(content=ANSWER)] * 3), label=label)

    chain = model("primary").with_fallbacks([model("fallback")])

    def with_retry(messages, config):
        while True:
            try:
                return chain.invoke(messages, config)
            except Exception:
                calls["retries"] += 1
                if calls["retries"] > 2:
                    raise

    llm = RunnableLambda(with_retry)

    class State(TypedDict, total=False):
        messages: list

    def generate(state):
        return {"messages": [llm.invoke("question")]}

    builder = StateGraph(State)
    builder.add_node("generate", generate)
    builder.add_edge(START, "generate")
    builder.add_edge("generate", END)
    graph = builder.compile()

    monkeypatch.setattr(build_graph, "get_compiled_graph", lambda: graph)
    return calls, produced


def _wait_until_still(produced: list, settle: float = 0.3, timeout: float = 5.0) -> int:
    """Waits until no new chunk arrived for `settle` seconds; returns the count."""
    deadline = time.monotonic() + timeout
    last = -1
    while time.monotonic() < deadline:
        n = len(produced)
        if n == last:
            return n
        last = n
        time.sleep(settle)
    return len(produced)


def test_closing_the_stream_stops_the_model(slow_graph):
    calls, produced = slow_graph
    stream = build_graph.stream_chat(thread_id="t-cancel", question="q")
    tokens = 0
    for kind, _ in stream:
        if kind == "token":
            tokens += 1
            if tokens == 3:
                break
    stream.close()

    total = _wait_until_still(produced)
    # The fake model yields a chunk per word and per space.
    assert total < 20, f"model kept generating after the stream was closed ({total} chunks)"
    assert calls == {"primary": 1, "fallback": 0, "retries": 0}


def test_a_stream_read_to_the_end_still_finishes(slow_graph, monkeypatch):
    monkeypatch.setattr(build_graph, "_build_sources", lambda docs: [])
    monkeypatch.setattr(build_graph, "_build_retrieval_diagnostics", lambda docs: [])
    calls, _ = slow_graph
    events = list(build_graph.stream_chat(thread_id="t-full", question="q"))
    names = [kind for kind, _ in events]
    assert names[-2:] == ["done", "contribution"]
    assert dict(events)["done"]["final_answer"] == ANSWER
    assert calls["primary"] == 1 and calls["retries"] == 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_client_that_disconnects_stops_the_model(app, slow_graph, monkeypatch):
    """The whole path: uvicorn, the /chat/stream route, a client that goes away."""
    import uvicorn

    from api import routes_chat

    monkeypatch.setattr(routes_chat, "_enforce_daily_budget", lambda: None)
    calls, produced = slow_graph

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        token = httpx.post(base + "/auth/guest").json()["access_token"]
        tokens = 0
        with httpx.stream(
            "POST",
            base + "/chat/stream",
            json={"message": "q"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        ) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data:") and "text" in json.loads(line[5:]):
                    tokens += 1
                    if tokens == 3:
                        break
        # Leaving the with-block closes the connection, like Stop in the widget.
        total = _wait_until_still(produced, settle=0.5)
        assert total < 60, f"model kept generating after the client left ({total} chunks)"
        assert calls["fallback"] == 0 and calls["retries"] == 0
    finally:
        server.should_exit = True
        thread.join(timeout=5)
