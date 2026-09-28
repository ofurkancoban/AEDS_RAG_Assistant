"""scripts/export_review_cases.py: mining golden-eval regression cases out
of real admin review decisions (a correction's factual diff, or a
rejection's candidate facts for human trimming)."""

import json

from db.models import AnswerStatus, CachedAnswer, SessionLocal
from scripts.export_review_cases import build_case, extract_facts, mine_review_cases


def test_extract_facts_finds_dates_ects_and_grades():
    text = "The deadline is 15 July 2026, worth 120 ECTS, minimum grade B2."
    facts = extract_facts(text)
    assert "15 July 2026" in facts
    assert "120 ECTS" in facts
    assert "B2" in facts


def test_extract_facts_ignores_boilerplate_sentence_openers():
    facts = extract_facts("The programme requires strong quantitative skills.")
    assert not any(f.lower().startswith("the ") for f in facts)


def test_extract_facts_deduplicates_case_insensitively():
    facts = extract_facts("120 ECTS is required. Also 120 ECTS for the thesis.")
    assert facts.count("120 ECTS") == 1


def _make_answer(**overrides) -> CachedAnswer:
    defaults = dict(
        question="What are the compulsory courses?",
        question_normalized="what are the compulsory courses?",
        embedding="[]",
        answer="Answer text",
        status=AnswerStatus.PENDING,
        sources_json=json.dumps(["catalog"]),
    )
    defaults.update(overrides)
    return CachedAnswer(**defaults)


def test_build_case_for_a_correction_diffs_added_and_removed_facts():
    row = _make_answer(
        answer="The course requires 90 ECTS and a B2 certificate.",
        original_answer="The course requires 30 ECTS.",
        status=AnswerStatus.APPROVED,
    )
    row.id = 1
    case = build_case(row)
    assert case is not None
    assert "90 ECTS" in case["expected_contains"]
    assert "B2" in case["expected_contains"]
    assert "30 ECTS" in case["expected_absent"]
    assert case["expected_source_ids"] == ["catalog"]


def test_build_case_for_a_purely_cosmetic_correction_is_none():
    row = _make_answer(
        answer="The course requires 90 ECTS.",
        original_answer="The course requires  90 ECTS.",  # only whitespace differs
        status=AnswerStatus.APPROVED,
    )
    row.id = 2
    assert build_case(row) is None


def test_build_case_for_a_rejection_flags_needs_review():
    row = _make_answer(answer="The deadline is 15 July 2026.", status=AnswerStatus.REJECTED)
    row.id = 3
    case = build_case(row)
    assert case is not None
    assert case["needs_review"] is True
    assert "15 July 2026" in case["expected_absent"]
    assert case["expected_contains"] == []


def test_build_case_for_a_pending_answer_is_none():
    row = _make_answer(status=AnswerStatus.PENDING)
    row.id = 4
    assert build_case(row) is None


def test_mine_review_cases_writes_only_buildable_cases(tmp_path, monkeypatch):
    import scripts.export_review_cases as mod

    output = tmp_path / "golden_qa_review.json"
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)

    session = SessionLocal()
    try:
        session.add(_make_answer(
            answer="Requires 90 ECTS.", original_answer="Requires 30 ECTS.",
            status=AnswerStatus.APPROVED,
        ))
        session.add(_make_answer(question="Unrelated?", status=AnswerStatus.PENDING))
        session.commit()
    finally:
        session.close()

    result = mine_review_cases()

    assert result["added"] == 1
    assert output.exists()
    written = json.loads(output.read_text())
    assert len(written) == 1
    assert written[0]["expected_contains"] == ["90 ECTS"]


def test_mine_review_cases_dry_run_writes_nothing(tmp_path, monkeypatch):
    import scripts.export_review_cases as mod

    output = tmp_path / "golden_qa_review.json"
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)

    session = SessionLocal()
    try:
        session.add(_make_answer(
            answer="Requires 90 ECTS.", original_answer="Requires 30 ECTS.",
            status=AnswerStatus.APPROVED,
        ))
        session.commit()
    finally:
        session.close()

    mine_review_cases(dry_run=True)
    assert not output.exists()


def test_mine_review_cases_keeps_hand_trimmed_cases_unless_overwrite(tmp_path, monkeypatch):
    import scripts.export_review_cases as mod

    output = tmp_path / "golden_qa_review.json"
    hand_trimmed = [{"id": "review-corrected-1", "question": "x", "expected_contains": ["kept"]}]
    output.write_text(json.dumps(hand_trimmed))
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)

    session = SessionLocal()
    try:
        row = _make_answer(
            answer="Requires 90 ECTS.", original_answer="Requires 30 ECTS.",
            status=AnswerStatus.APPROVED,
        )
        session.add(row)
        session.commit()
        real_id = row.id
    finally:
        session.close()

    monkeypatch.setattr(mod, "load_existing", lambda: [
        {"id": f"review-corrected-{real_id}", "question": "x", "expected_contains": ["kept"]}
    ])

    result = mine_review_cases()
    assert result["skipped"] == 1
    written = json.loads(output.read_text())
    assert written[0]["expected_contains"] == ["kept"]
