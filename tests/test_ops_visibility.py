"""Seeing problems before a student does: the admin status card, the
once-a-day alerts, Question Log rows turned into eval cases, canteen photos
on Telegram and the menu prefetch."""

import json
from datetime import date, datetime, timezone

import pytest

import llm_budget
import ops_alerts
from db.models import AnswerCheck, OpsAlertSent, ProviderDailyUsage, QueryLog, SessionLocal


@pytest.fixture
def sent(monkeypatch):
    """Alerts sent synchronously into a list."""
    import threading

    from api import telegram_bot

    messages = []
    monkeypatch.setattr(telegram_bot, "_notify_admins", lambda text, *a, **kw: messages.append(text))

    class Inline:
        def __init__(self, target, daemon=None, **kw):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(threading, "Thread", Inline)
    session = SessionLocal()
    session.query(OpsAlertSent).delete()
    session.commit()
    session.close()
    return messages


def test_an_alert_is_sent_once_a_day(sent):
    ops_alerts.alert_once_per_day("k", "first")
    ops_alerts.alert_once_per_day("k", "again")
    ops_alerts.alert_once_per_day("other", "different problem")
    assert sent == ["first", "different problem"]

    session = SessionLocal()
    session.get(OpsAlertSent, "k").day = "2000-01-01"
    session.commit()
    session.close()
    ops_alerts.alert_once_per_day("k", "next day")
    assert sent[-1] == "next day"


def test_the_main_model_warns_at_80_percent(sent, monkeypatch):
    monkeypatch.setattr(llm_budget, "daily_budget", lambda provider=None: 10)
    session = SessionLocal()
    session.query(ProviderDailyUsage).filter(ProviderDailyUsage.provider == "lowtest").delete()
    session.commit()
    session.close()
    for _ in range(7):
        llm_budget.record_call("lowtest")
    assert sent == []
    llm_budget.record_call("lowtest")
    llm_budget.record_call("lowtest")
    assert len(sent) == 1 and "8 of its 10" in sent[0]


def test_a_used_up_cloudflare_allocation_alerts_and_shows_in_the_status(sent, monkeypatch, client, admin_headers):
    import httpx

    from config import settings
    from db import reranker

    monkeypatch.setattr(settings, "cloudflare_account_id", "acct")
    monkeypatch.setattr(settings, "cloudflare_api_token", "token")
    monkeypatch.setattr(reranker, "_api_down_until", 0.0)
    request = httpx.Request("POST", "https://api.cloudflare.com/x")

    def used_up(*a, **kw):
        response = httpx.Response(429, text='{"errors":[{"code":4006}]}', request=request)
        raise httpx.HTTPStatusError("429", request=request, response=response)

    monkeypatch.setattr(httpx, "post", used_up)
    assert reranker._api_scores("q", ["a", "b"]) is None
    assert len(sent) == 1 and "free daily allocation" in sent[0]

    status = client.get("/admin/ops-status", headers=admin_headers).json()
    assert status["reranker"]["state"] == "paused" and status["reranker"]["reason"] == "allocation"
    assert status["reranker"]["until"]


def test_the_status_card_counts_today(client, admin_headers):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = SessionLocal()
    before = client.get("/admin/ops-status", headers=admin_headers).json()["today"]
    session.add_all([
        QueryLog(question="a", thread_id="ops-1", latency_ms=2000, answered=True, created_at=now),
        QueryLog(question="b", thread_id="ops-2", latency_ms=4000, answered=False, rating=-1, created_at=now),
        AnswerCheck(question="b", question_normalized="b", answer="x", findings_json=json.dumps(["made up"]), created_at=now),
        AnswerCheck(question="a", question_normalized="a", answer="x", findings_json="[]", created_at=now),
    ])
    session.commit()
    session.close()
    today = client.get("/admin/ops-status", headers=admin_headers).json()["today"]
    assert today["questions"] == before["questions"] + 2
    assert today["unanswered"] == before["unanswered"] + 1
    assert today["downvotes"] == before["downvotes"] + 1
    assert today["flagged_checks"] == before["flagged_checks"] + 1
    assert today["avg_latency_ms"]


@pytest.fixture
def drafts(monkeypatch, tmp_path):
    from db import eval_cases

    path = tmp_path / "case_drafts.json"
    monkeypatch.setattr(eval_cases, "drafts_path", lambda: path)
    return path


def _log(question, thread):
    session = SessionLocal()
    row = QueryLog(question=question, thread_id=thread, latency_ms=1000)
    session.add(row)
    session.commit()
    row_id = row.id
    session.close()
    return row_id


def test_a_logged_question_becomes_an_eval_case(client, admin_headers, drafts):
    widget = "My ECTS Tracker progress (6/120 ECTS completed):\nEconomics (6/36 ECTS)\n\nQuestion: who create you ?"
    first = _log(widget, "eval-thread")
    follow_up = _log("and why?", "eval-thread")

    url = f"/admin/question-log/{first}/eval-case"
    assert client.post(url, headers=admin_headers, json={}).status_code == 400  # nothing to check
    response = client.post(url, headers=admin_headers, json={"expected_absent": ["Anthropic", " Google ", "Anthropic"], "notes": "Invented creator"})
    assert response.status_code == 200
    case = json.loads(drafts.read_text())[0]
    # The question exactly as sent, so the eval replays what the model saw.
    assert case["id"] == f"log-{first}" and case["question"] == widget
    assert case["expected_absent"] == ["Anthropic", "Google"] and "needs_review" not in case
    assert client.post(f"/admin/question-log/{follow_up}/eval-case", headers=admin_headers, json={"expected_absent": ["x"]}).status_code == 400

    items = client.get("/admin/question-log", headers=admin_headers, params={"days": 1, "search": "who create"}).json()["items"]
    assert any(i["id"] == first and i["eval_case"] for i in items)


def test_admin_written_drafts_run_in_the_eval_and_can_be_committed(drafts, monkeypatch, tmp_path):
    from scripts import pull_eval_cases
    from tests import eval_golden

    drafts.write_text(json.dumps([
        {"id": "log-1", "question": "q1", "expected_contains": [], "expected_absent": ["Anthropic"]},
        {"id": "review-rejected-9", "question": "q2", "expected_contains": [], "expected_absent": [], "needs_review": True},
    ]))
    monkeypatch.setattr(eval_golden, "REVIEW_SET_PATH", tmp_path / "missing.json")
    ids = {c["id"] for c in eval_golden.load_cases()}
    assert "log-1" in ids and "review-rejected-9" not in ids

    merged, added = pull_eval_cases.merge(json.loads(drafts.read_text()), [{"id": "old"}], set())
    assert added == ["log-1"] and [c["id"] for c in merged] == ["old", "log-1"]
    assert pull_eval_cases.merge(json.loads(drafts.read_text()), merged, set())[1] == []


def test_menu_photos_go_to_telegram_as_an_album(monkeypatch, tmp_path):
    from api import routes_mensa, telegram_bot

    monkeypatch.setattr(telegram_bot, "_enabled", lambda: True)
    monkeypatch.setattr(routes_mensa, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(routes_mensa.httpx, "get", lambda url, **kw: routes_mensa.httpx.Response(200, content=b"jpg", headers={"content-type": "image/jpeg"}))
    posts = []

    class Ok:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(telegram_bot.requests, "post", lambda url, **kw: posts.append((url, kw)) or Ok())
    meal = {"name": "Pasta bake", "image": "assets/fotos/a/b.jpg", "side": False,
            "prices": {"students": "2,50"}, "pictogram_labels": [{"label": "vegetarian"}]}
    menu = {"menus": [{"meals": [meal, {**meal, "name": "Curry", "image": "assets/fotos/a/c.jpg"},
                                 {**meal, "name": "Soup", "side": True}, {**meal, "name": "No photo", "image": None}]}]}
    telegram_bot.send_menu_photos("123", menu)

    url, kw = posts[0]
    assert url.endswith("/sendMediaGroup")
    media = json.loads(kw["data"]["media"])
    assert [m["caption"] for m in media] == ["Pasta bake\n2,50 € (students) · vegetarian", "Curry\n2,50 € (students) · vegetarian"]
    assert set(kw["files"]) == {"p0", "p1"}


def test_the_prefetch_loads_menus_and_photos(monkeypatch):
    from api import routes_mensa
    from ingestion import mensa

    loaded, photos = [], []
    meal = mensa.Meal(name="x", counter="C", prices={}, codes=[], pictograms=["V"], image="assets/fotos/a.jpg", side=False)
    monkeypatch.setattr(mensa, "get_legend", lambda lang="en", force=False: loaded.append(("legend", lang, force)))
    monkeypatch.setattr(mensa, "get_menu", lambda loc, day, lang="en", force=False: loaded.append((loc, lang, force)) or ([meal], []))
    monkeypatch.setattr(routes_mensa, "cached_image", lambda src: photos.append(src))

    assert mensa.prefetch(date(2026, 10, 20)) == 4
    assert all(item[-1] is True for item in loaded) and len(loaded) == 6
    assert photos == ["assets/fotos/a.jpg", "assets/icons/V.png"] * 2
