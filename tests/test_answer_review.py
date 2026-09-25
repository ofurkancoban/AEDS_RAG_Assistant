"""The review gate: an answer is not reusable until an admin has approved it.

This is the system's one defence against a single bad generation being handed
to every student who later asks the same question, so it gets tested at both
levels: the store itself, and end to end through /chat.
"""

import json

import pytest

from db import semantic_cache
from db.models import AnswerStatus, CachedAnswer, SessionLocal
from tests.conftest import STUB_ANSWER, STUB_EMBEDDING

QUESTION = "Which courses are compulsory?"


def _seed_answer(question=QUESTION, answer="Cached reply.", status=AnswerStatus.PENDING):
    session = SessionLocal()
    try:
        row = CachedAnswer(
            question=question,
            question_normalized=semantic_cache._normalize(question),
            embedding=json.dumps(list(STUB_EMBEDDING)),
            answer=answer,
            original_answer=answer,
            sources_json=json.dumps([{"source_id": "catalog", "page": None, "url": None}]),
            retrieval_json="[]",
            status=status,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


@pytest.mark.parametrize("status", [AnswerStatus.PENDING, AnswerStatus.REJECTED])
def test_unapproved_answers_are_never_served(status):
    _seed_answer(status=status)
    session = SessionLocal()
    try:
        assert semantic_cache.lookup(session, QUESTION, list(STUB_EMBEDDING)) is None
    finally:
        session.close()


def test_approved_answers_are_served(client):
    _seed_answer(status=AnswerStatus.APPROVED)
    session = SessionLocal()
    try:
        hit = semantic_cache.lookup(session, QUESTION, list(STUB_EMBEDDING))
        assert hit is not None and hit.answer == "Cached reply."
    finally:
        session.close()


def test_a_question_is_queued_once_however_often_it_is_asked(client, guest_headers):
    for _ in range(3):
        client.post("/chat", json={"message": QUESTION}, headers=guest_headers)

    session = SessionLocal()
    try:
        rows = session.query(CachedAnswer).all()
        # Three students asking the same thing must not create three identical
        # entries for one admin to review.
        assert len(rows) == 1
        assert rows[0].status == AnswerStatus.PENDING
    finally:
        session.close()


def test_a_pending_answer_is_not_replayed_through_the_api(client, guest_headers):
    first = client.post("/chat", json={"message": QUESTION}, headers=guest_headers)
    assert first.json()["cached"] is False

    second = client.post("/chat", json={"message": QUESTION}, headers=guest_headers)
    # It is in the queue now, but unreviewed - so it must still be generated
    # rather than served back.
    assert second.json()["cached"] is False
    assert second.json()["answer"] == STUB_ANSWER


def test_an_approved_correction_is_what_later_askers_receive(client, guest_headers, admin_headers):
    answer_id = _seed_answer(answer="Wrong answer from the model.")

    approved = client.post(
        f"/admin/answers/{answer_id}/approve",
        json={"answer": "The four compulsory modules are A, B, C and D.", "admin_note": "fixed"},
        headers=admin_headers,
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["edited"] is True
    # The model's version is kept, so a correction can always be compared
    # against what actually went out.
    assert body["original_answer"] == "Wrong answer from the model."

    served = client.post("/chat", json={"message": QUESTION}, headers=guest_headers)
    assert served.json()["cached"] is True
    assert served.json()["answer"] == "The four compulsory modules are A, B, C and D."


def test_rejecting_keeps_the_record_but_stops_it_being_served(client, guest_headers, admin_headers):
    answer_id = _seed_answer(status=AnswerStatus.APPROVED)

    rejected = client.post(
        f"/admin/answers/{answer_id}/reject", json={"admin_note": "wrong"}, headers=admin_headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    session = SessionLocal()
    try:
        # A question the assistant got wrong is the most useful thing there is
        # to turn into a regression case, so the row must survive.
        assert session.get(CachedAnswer, answer_id) is not None
    finally:
        session.close()

    served = client.post("/chat", json={"message": QUESTION}, headers=guest_headers)
    assert served.json()["cached"] is False


def test_corpus_changes_demote_approved_answers_instead_of_deleting_them():
    answer_id = _seed_answer(answer="Admin's own wording.", status=AnswerStatus.APPROVED)

    moved = semantic_cache.invalidate_all()
    assert moved == 1

    session = SessionLocal()
    try:
        row = session.get(CachedAnswer, answer_id)
        # Deleting would throw away the admin's correction - the very work this
        # queue exists to collect.
        assert row.answer == "Admin's own wording."
        assert row.status == AnswerStatus.PENDING
        assert row.reviewed_at is None
    finally:
        session.close()


def test_the_review_queue_is_admin_only(client, guest_headers):
    answer_id = _seed_answer()

    assert client.get("/admin/answers").status_code == 401
    assert client.get("/admin/answers", headers=guest_headers).status_code == 403
    assert client.post(
        f"/admin/answers/{answer_id}/approve", json={}, headers=guest_headers
    ).status_code == 403
    assert client.delete(f"/admin/answers/{answer_id}", headers=guest_headers).status_code == 403


def test_the_queue_can_be_filtered_by_status(client, admin_headers):
    _seed_answer(question="First question?", status=AnswerStatus.PENDING)
    _seed_answer(question="Second question?", status=AnswerStatus.APPROVED)

    pending = client.get("/admin/answers?status_filter=pending", headers=admin_headers).json()
    every = client.get("/admin/answers?status_filter=all", headers=admin_headers).json()
    assert len(pending) == 1 and len(every) == 2

    bad = client.get("/admin/answers?status_filter=nonsense", headers=admin_headers)
    assert bad.status_code == 400
