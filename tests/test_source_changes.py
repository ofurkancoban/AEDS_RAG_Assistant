"""Admin surface for scripts/source_refresh.py's findings: the plain
Dismiss-only flow every source gets, and the LLM-drafted auto-update a small
allowlist also gets (api/telegram_bot.py's "Approve draft"/"Reject draft"
buttons, mirrored here for the web panel - see routes_admin.py)."""

from datetime import datetime, timezone

import pytest

from db.models import IngestedDocument, SessionLocal


def _seed_document(filename: str, *, diff: str | None = None, draft: str | None = None):
    session = SessionLocal()
    try:
        doc = IngestedDocument(
            filename=filename, file_hash="hash", chunk_count=1,
            source_diff=diff, source_draft=draft,
            last_changed_at=datetime.now(timezone.utc),
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc.id
    finally:
        session.close()


@pytest.fixture
def documents_dir(tmp_path, monkeypatch):
    """Redirects the file the approve-draft endpoint writes to a throwaway
    directory - without this a test would write into the real
    data/documents/ on whatever machine runs the suite."""
    from api import routes_admin

    monkeypatch.setattr(routes_admin.settings, "documents_dir", tmp_path)
    return tmp_path


@pytest.fixture
def stub_ingest(monkeypatch):
    """Records calls instead of actually embedding into Chroma - same
    reasoning as test_api_admin.py's corpus fixture."""
    from api import routes_admin

    calls = []
    monkeypatch.setattr(
        routes_admin, "ingest_and_record_file", lambda path, session: calls.append(path) or 1
    )
    return calls


def test_a_source_change_without_a_draft_reports_none(client, admin_headers):
    _seed_document("plain.md", diff="- old\n+ new")

    body = client.get("/admin/source-changes", headers=admin_headers).json()

    assert len(body) == 1
    assert body[0]["filename"] == "plain.md"
    assert body[0]["draft"] is None


def test_an_auto_draft_eligible_source_reports_its_draft(client, admin_headers):
    _seed_document("AEDS_website_language_requirements.md", diff="- old\n+ new", draft="new curated text")

    body = client.get("/admin/source-changes", headers=admin_headers).json()

    assert body[0]["draft"] == "new curated text"


def test_approving_a_draft_writes_the_file_and_reingests(client, admin_headers, documents_dir, stub_ingest):
    _seed_document("draft.md", diff="- old\n+ new", draft="the new curated text")

    response = client.post("/admin/source-changes/draft.md/approve-draft", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "draft_approved"
    assert (documents_dir / "draft.md").read_text(encoding="utf-8") == "the new curated text"
    assert stub_ingest == [documents_dir / "draft.md"]


def test_approving_a_draft_clears_both_the_diff_and_the_draft(client, admin_headers, documents_dir, stub_ingest):
    doc_id = _seed_document("draft.md", diff="- old\n+ new", draft="the new curated text")

    client.post("/admin/source-changes/draft.md/approve-draft", headers=admin_headers)

    session = SessionLocal()
    try:
        doc = session.get(IngestedDocument, doc_id)
        assert doc.source_diff is None
        assert doc.source_draft is None
    finally:
        session.close()


def test_rejecting_a_draft_discards_it_but_keeps_the_change_flagged(client, admin_headers):
    doc_id = _seed_document("draft.md", diff="- old\n+ new", draft="the new curated text")

    response = client.post("/admin/source-changes/draft.md/reject-draft", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "draft_rejected"

    session = SessionLocal()
    try:
        doc = session.get(IngestedDocument, doc_id)
        # Still flagged for the ordinary manual-dismiss review - only the
        # auto-draft is gone, same as Telegram's "sdrej" action.
        assert doc.source_diff == "- old\n+ new"
        assert doc.source_draft is None
    finally:
        session.close()


def test_approving_a_draft_that_does_not_exist_is_a_404(client, admin_headers):
    _seed_document("no-draft.md", diff="- old\n+ new")

    response = client.post("/admin/source-changes/no-draft.md/approve-draft", headers=admin_headers)

    assert response.status_code == 404


def test_rejecting_a_draft_that_does_not_exist_is_a_404(client, admin_headers):
    _seed_document("no-draft.md", diff="- old\n+ new")

    response = client.post("/admin/source-changes/no-draft.md/reject-draft", headers=admin_headers)

    assert response.status_code == 404


def test_draft_endpoints_are_closed_to_non_admins(client, guest_headers):
    _seed_document("draft.md", diff="- old\n+ new", draft="text")

    assert client.post("/admin/source-changes/draft.md/approve-draft", headers=guest_headers).status_code == 403
    assert client.post("/admin/source-changes/draft.md/reject-draft", headers=guest_headers).status_code == 403
