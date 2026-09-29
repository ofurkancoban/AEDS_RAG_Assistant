"""Admin surface: access control, revoking approved content, staff accounts.

The corpus side (Chroma) is stubbed. What is under test is the bookkeeping
around it - which calls are made, in what order, and what the database is left
looking like - not the vector store itself.
"""

import pytest

from db.models import PendingSubmission, Role, SessionLocal, SubmissionStatus, SubmissionType, User


@pytest.fixture
def corpus(monkeypatch):
    """Records the vector-store calls the admin routes make."""
    from api import routes_admin

    calls = {"ingested": [], "deleted": [], "restored": [], "deprecated": []}

    monkeypatch.setattr(
        routes_admin,
        "ingest_approved_submission",
        lambda content, source_id, submission_id: (
            calls["ingested"].append(submission_id) or f"chunk-{submission_id}"
        ),
    )
    monkeypatch.setattr(
        routes_admin,
        "delete_chunks_by_submission_id",
        lambda submission_id: (calls["deleted"].append(submission_id) or 1),
    )
    monkeypatch.setattr(
        routes_admin,
        "restore_chunk",
        lambda chunk_id: (calls["restored"].append(chunk_id) or True),
    )
    monkeypatch.setattr(
        routes_admin, "mark_deprecated", lambda chunk_id: calls["deprecated"].append(chunk_id)
    )
    return calls


def _seed_submission(user_id, submission_type=SubmissionType.NEW_INFO, related_chunk_id=None):
    session = SessionLocal()
    try:
        submission = PendingSubmission(
            submitted_by_id=user_id,
            submission_type=submission_type,
            source_id="general",
            content="A fact worth adding.",
            related_chunk_id=related_chunk_id,
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission.id
    finally:
        session.close()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/pending"),
        ("get", "/admin/stats"),
        ("get", "/admin/config"),
        ("get", "/admin/users"),
        ("get", "/admin/documents"),
        ("get", "/admin/analytics"),
        ("get", "/admin/origin-stats"),
    ],
)
def test_admin_screens_are_closed_to_visitors(client, guest_headers, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers=guest_headers).status_code == 403


def test_approving_a_submission_embeds_it(client, admin_headers, admin_user, corpus):
    submission_id = _seed_submission(admin_user.id)

    response = client.post(
        f"/admin/pending/{submission_id}/approve", json={}, headers=admin_headers
    )
    assert response.status_code == 200
    assert corpus["ingested"] == [submission_id]

    session = SessionLocal()
    try:
        assert session.get(PendingSubmission, submission_id).status == SubmissionStatus.APPROVED
    finally:
        session.close()


def test_revoking_removes_the_chunk_it_added(client, admin_headers, admin_user, corpus):
    submission_id = _seed_submission(admin_user.id)
    client.post(f"/admin/pending/{submission_id}/approve", json={}, headers=admin_headers)

    response = client.post(
        f"/admin/pending/{submission_id}/revoke", json={"admin_note": "mistake"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["chunks_deleted"] == 1
    assert corpus["deleted"] == [submission_id]

    session = SessionLocal()
    try:
        assert session.get(PendingSubmission, submission_id).status == SubmissionStatus.REVOKED
    finally:
        session.close()


def test_revoking_a_correction_puts_the_superseded_chunk_back(client, admin_headers, admin_user, corpus):
    submission_id = _seed_submission(
        admin_user.id, submission_type=SubmissionType.CORRECTION, related_chunk_id="old-chunk"
    )
    client.post(f"/admin/pending/{submission_id}/approve", json={}, headers=admin_headers)
    assert corpus["deprecated"] == ["old-chunk"]

    response = client.post(f"/admin/pending/{submission_id}/revoke", json={}, headers=admin_headers)
    # Without this the original stays hidden and the correction is gone, which
    # removes content nobody asked to remove.
    assert response.json()["original_chunk_restored"] is True
    assert corpus["restored"] == ["old-chunk"]


def test_only_approved_submissions_can_be_revoked(client, admin_headers, admin_user, corpus):
    submission_id = _seed_submission(admin_user.id)

    response = client.post(f"/admin/pending/{submission_id}/revoke", json={}, headers=admin_headers)
    assert response.status_code == 400
    assert corpus["deleted"] == []


def test_creating_a_staff_account(client, admin_headers):
    response = client.post(
        "/admin/users",
        json={"email": "Colleague@Example.com", "password": "long-enough-password", "role": "admin"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    # Stored normalised, or the same person becomes two accounts and login
    # fails on the wrong capitalisation.
    assert response.json()["email"] == "colleague@example.com"

    duplicate = client.post(
        "/admin/users",
        json={"email": "colleague@example.com", "password": "long-enough-password"},
        headers=admin_headers,
    )
    assert duplicate.status_code == 400


def test_staff_accounts_need_a_real_password(client, admin_headers):
    response = client.post(
        "/admin/users", json={"email": "weak@example.com", "password": "abc"}, headers=admin_headers
    )
    assert response.status_code == 400


def test_an_admin_cannot_demote_themselves(client, admin_headers, admin_user):
    response = client.patch(
        f"/admin/users/{admin_user.id}", json={"role": "user"}, headers=admin_headers
    )
    # Otherwise the only way back is the command line.
    assert response.status_code == 400


def test_the_last_admin_cannot_be_demoted_or_deleted(client, admin_headers, admin_user):
    from tests.conftest import _make_user

    other_admin = _make_user("second@example.com", "long-enough-password", Role.ADMIN)

    # With two admins, demoting the other one is allowed.
    assert client.patch(
        f"/admin/users/{other_admin.id}", json={"role": "user"}, headers=admin_headers
    ).status_code == 200

    # Now the caller is the last admin left, and cannot be removed by anyone.
    assert client.delete(f"/admin/users/{admin_user.id}", headers=admin_headers).status_code == 400


def test_anonymous_sessions_are_counted_not_listed(client, admin_headers, guest_headers):
    body = client.get("/admin/users", headers=admin_headers).json()
    assert body["anonymous_sessions"] >= 1
    assert all(not u["email"].startswith("guest-") for u in body["users"])


def test_a_guest_row_is_not_a_manageable_account(client, admin_headers, guest_headers):
    guest_id = client.get("/auth/me", headers=guest_headers).json()["id"]

    response = client.patch(f"/admin/users/{guest_id}", json={"role": "admin"}, headers=admin_headers)
    assert response.status_code == 400


def test_an_account_with_submissions_is_not_silently_deleted(client, admin_headers, admin_user):
    from tests.conftest import _make_user

    contributor = _make_user("contributor@example.com", "long-enough-password", Role.USER)
    _seed_submission(contributor.id)

    response = client.delete(f"/admin/users/{contributor.id}", headers=admin_headers)
    # submitted_by_id is NOT NULL, so deleting would orphan the submissions.
    assert response.status_code == 400
    assert "submitted" in response.json()["detail"]

    session = SessionLocal()
    try:
        assert session.get(User, contributor.id) is not None
    finally:
        session.close()


def test_deleting_an_account_keeps_its_reviews_de_attributed(client, admin_headers, admin_user, corpus):
    from tests.conftest import _make_user

    reviewer = _make_user("reviewer@example.com", "long-enough-password", Role.ADMIN)
    submission_id = _seed_submission(admin_user.id)

    session = SessionLocal()
    try:
        submission = session.get(PendingSubmission, submission_id)
        submission.reviewed_by_id = reviewer.id
        session.commit()
    finally:
        session.close()

    assert client.delete(f"/admin/users/{reviewer.id}", headers=admin_headers).status_code == 200

    session = SessionLocal()
    try:
        # The decision still happened, so the row stays - just unattributed.
        assert session.get(PendingSubmission, submission_id).reviewed_by_id is None
    finally:
        session.close()


def test_stats_report_the_model_actually_answering(client, admin_headers):
    from runtime_config import active_chat_model

    body = client.get("/admin/stats", headers=admin_headers).json()
    assert body["llm_model"] == active_chat_model()
    assert "pending_answers" in body
