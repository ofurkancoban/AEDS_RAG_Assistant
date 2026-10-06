"""/chat/threads lists a visitor's own conversations, and /chat/threads/{id}
reopens one with the sources and passages each answer was shown with."""

from api import routes_chat


def _fake_stream(answer: str, source_id: str):
    def fake(thread_id, question, source_id_filter=None):
        yield ("token", {"text": answer})
        yield ("done", {
            "sources": [{"source_id": source_id, "page": None, "url": None}],
            "final_answer": answer,
            "retrieval": [{"source_id": source_id, "snippet": "passage text", "hybrid_score": 0.5, "rerank_score": 0.9}],
            "node_latencies": {},
            "answered": True,
            "time_sensitive": False,
            "has_expired_deadline": False,
        })
        yield ("contribution", {"detected_contribution": None})
    return fake


def _ask(client, headers, monkeypatch, question, answer, source_id, thread_id=None):
    monkeypatch.setattr(routes_chat, "stream_chat", _fake_stream(answer, source_id))
    response = client.post("/chat/stream", json={"message": question, "thread_id": thread_id}, headers=headers)
    assert response.status_code == 200
    done = [block for block in response.text.split("\n\n") if block.startswith("event: done")][0]
    import json

    return json.loads(done.split("data:", 1)[1])


def test_lists_threads_newest_first_titled_by_first_question(client, guest_headers, monkeypatch):
    first = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90 [1].", "fees")
    _ask(client, guest_headers, monkeypatch, "And the ticket?", "EUR 230.80 [1].", "ticket", first["thread_id"])
    second = _ask(client, guest_headers, monkeypatch, "When is the library open?", "Until 24:00 [1].", "library")

    threads = client.get("/chat/threads", headers=guest_headers).json()

    assert [t["thread_id"] for t in threads] == [second["thread_id"], first["thread_id"]]
    assert threads[1]["title"] == "How much is the semester fee?"
    assert threads[1]["questions"] == 2


def test_reopened_thread_keeps_each_answers_passages_in_order(client, guest_headers, monkeypatch):
    first = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90 [1].", "fees")
    _ask(client, guest_headers, monkeypatch, "And the ticket?", "EUR 230.80 [1].", "ticket", first["thread_id"])

    turns = client.get(f"/chat/threads/{first['thread_id']}", headers=guest_headers).json()

    assert [t["question"] for t in turns] == ["How much is the semester fee?", "And the ticket?"]
    assert turns[1]["answer"] == "EUR 230.80 [1]."
    assert turns[1]["retrieval"][0]["source_id"] == "ticket"
    assert turns[0]["query_log_id"] == first["query_log_id"]


def test_another_visitor_cannot_list_or_open_my_thread(client, guest_headers, other_guest_headers, monkeypatch):
    mine = _ask(client, guest_headers, monkeypatch, "How much is the semester fee?", "EUR 457.90.", "fees")

    assert client.get("/chat/threads", headers=other_guest_headers).json() == []
    response = client.get(f"/chat/threads/{mine['thread_id']}", headers=other_guest_headers)
    assert response.status_code == 404
