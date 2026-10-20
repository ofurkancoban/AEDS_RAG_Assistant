"""ECTS Tracker widget answers (computed figures, the check's context),
rule-based routing and the review-draft miner."""

from graph import nodes
from graph.answer_check import _with_student_progress

PROGRESS = (
    "My ECTS Tracker progress (48/120 ECTS completed):\n"
    "Economics (18/36 ECTS) - completed: wir874 - Advanced Microeconomics | in progress: wir873 - Applied Economics; "
    "wir895 - Industrial Organization; wir901 - Environmental Economics\n"
    "Thesis (0/30 ECTS) - planned: mam - Master's Degree Module\n\n"
    "Question: Where do I stand?"
)


def test_progress_figures_say_what_is_completed_and_what_is_covered(monkeypatch):
    monkeypatch.setattr(nodes, "get_catalog_courses", lambda: [
        {"code": c, "ects": e} for c, e in [("wir873", 6), ("wir895", 6), ("wir901", 6), ("mam", 30)]
    ])
    facts = nodes._progress_facts(PROGRESS)
    assert ("- Economics: 18 of 36 ECTS completed, 18 ECTS in progress, 0 ECTS planned; 18 ECTS not yet "
            "completed (covered once the courses in progress and planned are passed).") in facts
    # "mam" has no digits and used to be skipped.
    assert "- Thesis: 0 of 30 ECTS completed, 0 ECTS in progress, 30 ECTS planned" in facts
    assert "- Data Science: 0 of 18 ECTS completed" in facts and "18 ECTS not yet covered by any course" in facts
    assert nodes._progress_facts("How do I register?") is None


def test_the_check_reads_the_progress_block_as_context():
    question, context = _with_student_progress(PROGRESS, "DOCS")
    assert question == "Where do I stand?"
    assert context.startswith("The student's own course progress") and "wir874" in context and context.endswith("DOCS")
    assert _with_student_progress("plain?", "DOCS") == ("plain?", "DOCS")


def test_teaching_questions_are_routed_without_the_model(monkeypatch):
    monkeypatch.setattr(nodes, "get_catalog_courses", lambda: [
        {"code": "wir874", "name": "Advanced Microeconomics", "professor": "Carsten Helm", "ects": 6},
        {"code": "inf535", "name": "Computational Intelligence I", "professor": "Oliver Kramer", "ects": 6},
    ])
    assert nodes._obvious_route("Who teaches Advanced Microeconomics?") == [
        {"name": "search_course_catalog", "args": {"course_name_or_abbreviation": "Advanced Microeconomics"}}
    ]
    assert nodes._obvious_route("Which courses does Carsten Helm teach?") == [
        {"name": "search_course_catalog", "args": {"professor_name": "Carsten Helm"}}
    ]
    for question in ("Who is Carsten Helm?", "Does Helm teach Advanced Microeconomics?", "When is the deadline?"):
        assert nodes._obvious_route(question) is None


def test_widget_questions_are_gated_on_the_question_alone(monkeypatch):
    from langchain_core.messages import HumanMessage

    asked = []
    monkeypatch.setattr(nodes, "_route_with_tools", lambda q: asked.append(q))
    monkeypatch.setattr(nodes, "_SpeculativeRetrieval", lambda q, f: type("R", (), {"result": lambda self: [], "cancel": lambda self: None})())
    nodes.retrieve_node({"messages": [HumanMessage(content=PROGRESS)], "source_id_filter": None})
    assert asked == ["Where do I stand?"]


def test_rejected_personal_or_small_talk_answers_are_not_drafted():
    from db.models import AnswerStatus, CachedAnswer
    from scripts.export_review_cases import build_case

    row = CachedAnswer(id=1, question=PROGRESS, question_normalized="x", answer="Which semester?", status=AnswerStatus.REJECTED, sources_json="[]")
    assert build_case(row) is None
    row = CachedAnswer(id=2, question="hi", question_normalized="hi", answer="Hi!", status=AnswerStatus.REJECTED, sources_json="[]")
    assert build_case(row) is None
