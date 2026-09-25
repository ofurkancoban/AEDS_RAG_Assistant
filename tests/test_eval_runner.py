"""The golden-eval checker itself.

An eval that mis-grades is worse than no eval: it either hides a regression or
sends someone chasing one that is not there. These are the grading rules, not
the answers.
"""

from tests.eval_golden import check_case

RETRIEVAL = [{"source_id": "catalog"}, {"source_id": "MPO_AEDS_2023_EN"}]


def _result(answer="The thesis is worth 30 ECTS.", retrieval=None, contribution=None):
    return {
        "answer": answer,
        "retrieval": RETRIEVAL if retrieval is None else retrieval,
        "detected_contribution": contribution,
    }


def test_formatting_cannot_fail_a_content_assertion():
    # "**fourth** semester" stopped containing "fourth semester" the day the
    # assistant started bolding the value that answers the question.
    result = _result(answer="Register in the **fourth** semester.")
    assert check_case(result, {"expected_contains": ["fourth semester"]}) == []


def test_alternative_wordings_satisfy_one_expectation():
    case = {"expected_contains": [["twice", "two times"]]}
    assert check_case(_result(answer="You may resit two times."), case) == []
    assert check_case(_result(answer="You may resit once."), case) != []


def test_forbidden_terms_are_reported():
    problems = check_case(_result(answer="Applicants need a DSH 3 certificate."), {"expected_absent": ["DSH 3"]})
    assert len(problems) == 1
    assert "forbidden" in problems[0]


def test_a_named_source_must_have_been_retrieved():
    assert check_case(_result(), {"expected_source_ids": ["catalog"]}) == []
    assert check_case(_result(), {"expected_source_ids": ["semester_planning_rules"]}) != []


def test_any_one_of_several_authoritative_sources_satisfies_the_assertion():
    # The thesis ECTS is stated in both the module handbook and the planning
    # rules; answering from either is correct.
    case = {"expected_source_ids": [["MPO_AEDS_2023_EN", "semester_planning_rules"]]}
    assert check_case(_result(), case) == []

    wrong_source = _result(retrieval=[{"source_id": "AEDS_website_theses_faq"}])
    # The generic university-wide FAQ is not one of them, and answering from it
    # is exactly the failure this assertion exists to catch.
    assert check_case(wrong_source, case) != []


def test_a_case_with_no_source_assertion_ignores_retrieval_entirely():
    # Questions answered by the SQL tools never touch the vector store.
    assert check_case(_result(retrieval=[]), {"expected_contains": ["30"]}) == []


def test_contribution_flagging_is_checked_separately_from_the_answer():
    flagged = _result(contribution={"type": "new_info", "content": "..."})
    assert check_case(flagged, {"expected_contribution": "new_info"}) == []
    assert check_case(flagged, {"expected_contribution": None}) != []
    assert check_case(_result(), {"expected_contribution": None}) == []
