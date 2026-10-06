"""/chat/stream sends the answer's 'done' event before contribution
detection has finished, then a separate 'contribution' event - so the
sources appear as soon as the answer does."""

import json

from api import routes_chat
from db.models import PendingSubmission, SessionLocal


def _events(response_text: str) -> list[tuple[str, dict]]:
    events = []
    for block in response_text.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if name:
            events.append((name, data))
    return events


def _fake_stream(detected):
    def fake(thread_id, question, source_id_filter=None):
        yield ("stage", {"stage": "understanding"})
        yield ("token", {"text": "The lab "})
        yield ("token", {"text": "is in A14 [1]."})
        yield ("done", {
            "sources": [{"source_id": "stub", "page": None, "url": None}],
            "final_answer": "The lab is in A14 [1].",
            "retrieval": [],
            "node_latencies": {"generate": 1.0},
            "answered": True,
            "time_sensitive": False,
            "has_expired_deadline": False,
        })
        yield ("contribution", {"detected_contribution": detected})
    return fake


def _submissions() -> int:
    session = SessionLocal()
    try:
        return session.query(PendingSubmission).count()
    finally:
        session.close()


def test_done_arrives_before_contribution_and_flags_it(client, guest_headers, monkeypatch):
    monkeypatch.setattr(routes_chat, "stream_chat", _fake_stream({"type": "new_info", "content": "The lab is in A14."}))

    response = client.post("/chat/stream", json={"message": "The lab is in room A14."}, headers=guest_headers)

    names = [name for name, _ in _events(response.text)]
    assert names == ["stage", "token", "token", "done", "contribution"]
    done = dict(_events(response.text))["done"]
    assert done["auto_flagged_contribution"] is None and done["query_log_id"] is not None
    assert dict(_events(response.text))["contribution"] == {"auto_flagged_contribution": "new_info"}
    assert _submissions() == 1


def test_no_contribution_event_or_submission_when_nothing_is_detected(client, guest_headers, monkeypatch):
    monkeypatch.setattr(routes_chat, "stream_chat", _fake_stream(None))

    response = client.post("/chat/stream", json={"message": "Where is the lab?"}, headers=guest_headers)

    assert [name for name, _ in _events(response.text)][-1] == "done"
    assert _submissions() == 0
