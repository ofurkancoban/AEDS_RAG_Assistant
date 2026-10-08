"""Weekly golden-set runs are recorded and listed for the admin panel."""

import json

from db.models import EvalRun, SessionLocal


def test_recorded_runs_are_listed_newest_first(client, admin_headers):
    from scripts.eval_and_notify import _record_run

    _record_run("openrouter", "apodex/apodex-1.1-mini:free", 41, 47, ["a", "b"])
    _record_run("openrouter", "apodex/apodex-1.1-mini:free", 61, 64, ["c"])

    runs = client.get("/admin/eval-runs", headers=admin_headers).json()

    assert [(r["passed"], r["total"]) for r in runs[:2]] == [(61, 64), (41, 47)]
    assert runs[0]["failed_ids"] == ["c"]


def test_the_list_is_admin_only(client, guest_headers):
    assert client.get("/admin/eval-runs", headers=guest_headers).status_code in (401, 403)


def test_the_weekly_job_records_its_score(monkeypatch):
    from scripts import eval_and_notify

    monkeypatch.setattr(eval_and_notify, "mine_review_cases", lambda: {"added": 0, "needs_review": 0})
    monkeypatch.setattr(eval_and_notify, "load_cases", lambda: [{"id": "x"}, {"id": "y"}])
    sent = []
    monkeypatch.setattr(eval_and_notify, "_notify_admins", lambda text: sent.append(text))

    def fake_run(cases, verbose, report_path=None):
        report_path.write_text(json.dumps([{"id": "x", "passed": True}, {"id": "y", "passed": False}]))
        return False

    monkeypatch.setattr(eval_and_notify, "run", fake_run)
    assert eval_and_notify.main() == 1

    session = SessionLocal()
    try:
        row = session.query(EvalRun).order_by(EvalRun.id.desc()).first()
        assert (row.passed, row.total, json.loads(row.failed_ids_json)) == (1, 2, ["y"])
    finally:
        session.close()
    assert "1/2 passed" in sent[0] and "y" in sent[0]
