"""Mining the review queue for regression cases.

The point of the exporter is that a wrong answer an admin caught is worth more
as a permanent test than as a database row, so what matters here is that the
assertions it derives are honest: facts the correction actually changed, and
nothing invented.
"""

import json

from db.models import AnswerStatus, CachedAnswer, SessionLocal
from scripts.export_review_cases import build_case, extract_facts


def _row(**kwargs):
    defaults = dict(
        question="When is the application deadline?",
        question_normalized="when is the application deadline",
        embedding="[]",
        answer="",
        sources_json='[{"source_id": "deadlines", "page": null, "url": null}]',
        retrieval_json="[]",
        status=AnswerStatus.PENDING,
    )
    defaults.update(kwargs)
    session = SessionLocal()
    try:
        row = CachedAnswer(**defaults)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row
    finally:
        session.close()


def test_hard_facts_are_extracted_and_prose_is_not():
    facts = extract_facts(
        "The programme requires **120 ECTS** and English **B2**. "
        "Apply by 15 July 2026 under Section 8."
    )
    assert "120 ECTS" in facts
    assert "B2" in facts
    assert "15 July 2026" in facts
    assert "Section 8" in facts
    # Emphasis markers are stripped by the eval runner before matching, so a
    # term carrying them could never match.
    assert not any("*" in fact for fact in facts)


def test_sentence_openers_are_not_mistaken_for_names():
    facts = extract_facts("The programme is taught in English.")
    assert not any(fact.lower().startswith("the ") for fact in facts)


def test_a_correction_yields_both_what_was_missing_and_what_was_invented():
    row = _row(
        status=AnswerStatus.APPROVED,
        answer="The deadline is 15 July 2026 and the programme is 120 ECTS.",
        original_answer="The deadline is 1 March 2025 and the programme is 120 ECTS.",
    )

    case = build_case(row)
    assert case["id"] == f"review-corrected-{row.id}"
    assert "15 July 2026" in case["expected_contains"]
    assert "1 March 2025" in case["expected_absent"]
    # Unchanged facts belong in neither list, or the case would assert things
    # the correction never spoke to.
    assert "120 ECTS" not in case["expected_contains"]
    assert "120 ECTS" not in case["expected_absent"]
    assert case["expected_source_ids"] == ["deadlines"]


def test_a_purely_cosmetic_edit_produces_no_case():
    row = _row(
        status=AnswerStatus.APPROVED,
        answer="The deadline is 15 July 2026.",
        original_answer="the deadline is 15 July 2026",
    )
    # Rewording is not a regression; a case built from one would fail on the
    # next equally-correct rewording.
    assert build_case(row) is None


def test_an_approved_answer_that_was_never_edited_produces_no_case():
    row = _row(status=AnswerStatus.APPROVED, answer="Correct first time.", original_answer=None)
    assert build_case(row) is None


def test_a_rejection_is_exported_but_flagged_for_human_trimming():
    row = _row(
        status=AnswerStatus.REJECTED,
        answer="The deadline is 1 March 2025.",
        admin_note="wrong cycle",
    )

    case = build_case(row)
    assert case["id"] == f"review-rejected-{row.id}"
    assert "1 March 2025" in case["expected_absent"]
    # There is no corrected text to diff against, so nothing here is verified.
    assert case["needs_review"] is True
    assert "wrong cycle" in case["notes"]


def test_pending_answers_are_not_exported():
    assert build_case(_row(status=AnswerStatus.PENDING, answer="Not reviewed yet.")) is None


def _export(tmp_path, monkeypatch, argv):
    import sys

    from scripts import export_review_cases

    output = tmp_path / "golden_qa_review.json"
    monkeypatch.setattr(export_review_cases, "OUTPUT_PATH", output)
    monkeypatch.setattr(sys, "argv", ["export_review_cases.py", *argv])
    export_review_cases.main()
    return output


def test_a_hand_trimmed_case_survives_a_re_export(tmp_path, monkeypatch):
    row = _row(
        status=AnswerStatus.REJECTED,
        answer="The deadline is 1 March 2025 and the programme is 120 ECTS.",
    )

    output = _export(tmp_path, monkeypatch, [])
    generated = json.loads(output.read_text(encoding="utf-8"))
    assert len(generated) == 1
    assert "120 ECTS" in generated[0]["expected_absent"]

    # A human decides the ECTS figure was actually right and removes it.
    generated[0]["expected_absent"] = ["1 March 2025"]
    generated[0]["needs_review"] = False
    output.write_text(json.dumps(generated), encoding="utf-8")

    _export(tmp_path, monkeypatch, [])
    kept = json.loads(output.read_text(encoding="utf-8"))
    # Re-running the export must not undo review work, or nobody will trust it
    # enough to run it twice.
    assert kept[0]["expected_absent"] == ["1 March 2025"]
    assert kept[0]["needs_review"] is False

    _export(tmp_path, monkeypatch, ["--overwrite"])
    rebuilt = json.loads(output.read_text(encoding="utf-8"))
    # --overwrite is the explicit way back to the generated version.
    assert "120 ECTS" in rebuilt[0]["expected_absent"]
    assert rebuilt[0]["id"] == f"review-rejected-{row.id}"


def test_a_dry_run_writes_nothing(tmp_path, monkeypatch):
    _row(status=AnswerStatus.REJECTED, answer="The deadline is 1 March 2025.")
    output = _export(tmp_path, monkeypatch, ["--dry-run"])
    assert not output.exists()


def test_untrimmed_cases_are_excluded_from_the_eval_run(tmp_path, monkeypatch):
    from tests import eval_golden

    review_file = tmp_path / "golden_qa_review.json"
    review_file.write_text(
        json.dumps(
            [
                {"id": "review-corrected-1", "question": "Q1", "expected_contains": ["x"]},
                {"id": "review-rejected-2", "question": "Q2", "expected_absent": ["y"], "needs_review": True},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_golden, "REVIEW_SET_PATH", review_file)

    ids = {case["id"] for case in eval_golden.load_cases()}
    assert "review-corrected-1" in ids
    # Failing on assertions nobody has vouched for would make the eval
    # untrustworthy, which is worse than not running them.
    assert "review-rejected-2" not in ids

    assert "review-corrected-1" not in {c["id"] for c in eval_golden.load_cases(include_review=False)}
