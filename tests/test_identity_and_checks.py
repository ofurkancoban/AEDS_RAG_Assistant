"""Who-are-you questions get a fixed answer (also from the ECTS Tracker
widget, whose messages carry a progress block), and every answer the
background check flagged is listed for admins, not only first answers."""

import json

import pytest
from langchain_core.messages import HumanMessage

from graph import nodes

WIDGET = (
    "My ECTS Tracker progress (48/120 ECTS completed):\nEconomics (18/36 ECTS) - completed: wir874 - "
    "Advanced Microeconomics; wir873\n\nQuestion: {q}"
)


@pytest.mark.parametrize("question", [
    "who create you ?", "who created you?", "who are you?", "which model are you?", "are you ChatGPT?",
    "what are you?", "Wer bist du?", "wer hat dich gebaut?",
])
def test_identity_questions_get_the_fixed_answer(question):
    reply = nodes._conversational_reply(question)
    assert reply and ("study assistant" in reply or "Studienassistent" in reply)
    assert "Anthropic" not in reply


@pytest.mark.parametrize("question", [
    "Who is the professor for EPE?", "who are the professors here?", "what are you studying?",
    "What model of thesis supervision is used?", "who made the module handbook?",
])
def test_real_questions_are_not_mistaken_for_identity_questions(question):
    assert nodes._conversational_reply(question) is None


def test_the_widget_question_is_read_without_its_progress_block():
    assert nodes.student_question(WIDGET.format(q="who create you ?")) == "who create you ?"
    assert nodes.student_question("Question: why is this so?") == "Question: why is this so?"
    out = nodes.retrieve_node({"messages": [HumanMessage(content=WIDGET.format(q="who create you ?"))], "source_id_filter": None})
    assert "study assistant" in out["direct_answer"]


def test_a_copied_source_label_is_removed_from_the_answer():
    assert nodes._strip_fabricated_citations("I was created by X [source: system message].") == "I was created by X."


def test_admins_see_every_flagged_answer_and_can_mark_it_seen(client, admin_headers):
    from db.models import AnswerCheck, SessionLocal

    session = SessionLocal()
    try:
        flagged = AnswerCheck(question=WIDGET.format(q="who create you ?"), question_normalized="x",
                              answer="I was created by Anthropic", findings_json=json.dumps(["created by Anthropic - not in the context"]))
        clean = AnswerCheck(question="How long is the thesis?", question_normalized="y", answer="6 months", findings_json="[]")
        session.add_all([flagged, clean])
        session.commit()
        flagged_id = flagged.id
    finally:
        session.close()

    rows = client.get("/admin/answer-checks", headers=admin_headers).json()
    mine = [r for r in rows if r["id"] == flagged_id]
    assert mine and mine[0]["question"] == "who create you ?"  # the progress block is left out
    assert all(r["findings"] for r in rows)  # clean checks are not listed

    assert client.post(f"/admin/answer-checks/{flagged_id}/seen", headers=admin_headers).status_code == 204
    assert flagged_id not in [r["id"] for r in client.get("/admin/answer-checks", headers=admin_headers).json()]


def test_answer_checks_are_admin_only(client):
    assert client.get("/admin/answer-checks").status_code in (401, 403)


def test_the_identity_answer_names_the_builder_once_and_telegram_keeps_the_link():
    from api.telegram_bot import _strip_markdown
    from graph.nodes import _conversational_reply

    for question in ("who created you?", "Wer hat dich entwickelt?"):
        reply = _conversational_reply(question)
        assert "Furkan Çoban" in reply and "https://github.com/ofurkancoban" in reply
        assert reply.count("M.Sc. Applied Economics and Data Science") == 1
    plain = _strip_markdown(_conversational_reply("who created you?"))
    assert "Furkan Çoban (https://github.com/ofurkancoban)" in plain and "](" not in plain


def test_admin_telegram_messages_drop_citation_markers_and_the_progress_block(monkeypatch):
    from api import telegram_bot

    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, *a, **kw: sent.append(text))
    widget = "My ECTS Tracker progress (6/120 ECTS completed):\nEconomics (6/36 ECTS)\n\nQuestion: How long is the thesis?"
    telegram_bot.notify_pending_answer(1, widget, "About **80 pages** [1][3], due in May [2].", chat_id="1")
    assert sent[0] == "Q: How long is the thesis?\n\nA: About 80 pages, due in May."
