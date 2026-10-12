"""The ECTS Tracker chat widget's opt-in course-context toggle tells us
exactly which courses a student already has (completed/in-progress/planned),
via a machine-readable line appended to the injected context. Before this,
the schedule-request branch in graph/nodes.py had no way to use that: it
always built a from-scratch, full-programme plan and indexed into it by a
stated semester number, so any sufficiently late semester number landed on
the thesis term regardless of what the student had actually finished. These
tests cover the pieces that fix that: parsing the codes line, computing each
category's remaining ECTS target, and excluding already-had courses from the
selection."""

from __future__ import annotations

from datetime import date

import pytest

from graph import nodes


def _course(
    code, category, ects, compulsory=False, offering=None, name=None,
    semesters_offered=None, extra_semesters=None,
    difficulty_avg=None, difficulty_count=None,
):
    return {
        "code": code,
        "category": category,
        "ects": ects,
        "compulsory": compulsory,
        "offering": offering,
        "name": name or code,
        "professor": "",
        "language": "en",
        "semesters_offered": semesters_offered,
        "extra_semesters": extra_semesters,
        "difficulty_avg": difficulty_avg,
        "difficulty_count": difficulty_count,
    }


class TestExtractCompletedCodes:
    def test_absent_line_returns_empty_set(self):
        assert nodes._extract_completed_codes("What should I take next semester?") == frozenset()

    def test_present_line_is_parsed_lowercased_and_deduplicated(self):
        text = (
            "My ECTS Tracker progress (12/120 ECTS completed):\n"
            "Economics (12/36 ECTS) - completed: wir821 - Advanced Microeconomics\n"
            "Codes already completed or in progress: WIR821, wir873, wir821\n"
            "What should I take next semester?"
        )
        assert nodes._extract_completed_codes(text) == frozenset({"wir821", "wir873"})

    def test_malformed_line_with_no_codes_returns_empty_set(self):
        text = "Codes already completed or in progress: \nWhat should I take next?"
        assert nodes._extract_completed_codes(text) == frozenset()


class TestComputeRemainingTargets:
    def test_empty_exclude_set_returns_targets_unchanged(self):
        assert nodes._compute_remaining_targets(frozenset()) == nodes._CATEGORY_ECTS_TARGETS

    def test_partial_completion_reduces_only_the_matching_category(self, monkeypatch):
        monkeypatch.setattr(
            nodes,
            "get_catalog_courses",
            lambda: [_course("wir821", "economics", 6, compulsory=True)],
        )
        targets = nodes._compute_remaining_targets(frozenset({"wir821"}))
        assert targets["economics"] == nodes._CATEGORY_ECTS_TARGETS["economics"] - 6
        assert targets["empirical"] == nodes._CATEGORY_ECTS_TARGETS["empirical"]

    def test_full_category_completion_floors_at_zero_not_negative(self, monkeypatch):
        monkeypatch.setattr(
            nodes,
            "get_catalog_courses",
            lambda: [_course("wir821", "economics", 999, compulsory=True)],
        )
        targets = nodes._compute_remaining_targets(frozenset({"wir821"}))
        assert targets["economics"] == 0

    def test_thesis_code_zeroes_the_thesis_target(self, monkeypatch):
        monkeypatch.setattr(
            nodes,
            "get_catalog_courses",
            lambda: [_course("mam", "thesis", 30, compulsory=True)],
        )
        targets = nodes._compute_remaining_targets(frozenset({"mam"}))
        assert targets["thesis"] == 0

    def test_codes_by_category_overrides_the_catalogs_own_category(self, monkeypatch):
        # inf535/inf536 are filed under "datascience" in this catalog, but
        # the student's own ECTS Tracker counts them toward "specialization"
        # - a legitimate cross-listed-elective flexibility the catalog's
        # single fixed category per course can't represent on its own.
        monkeypatch.setattr(
            nodes,
            "get_catalog_courses",
            lambda: [_course("inf535", "datascience", 6, compulsory=False)],
        )
        exclude = frozenset({"inf535"})
        codes_by_category = {"specialization": frozenset({"inf535"})}
        targets = nodes._compute_remaining_targets(exclude, codes_by_category)
        assert targets["specialization"] == nodes._CATEGORY_ECTS_TARGETS["specialization"] - 6
        assert targets["datascience"] == nodes._CATEGORY_ECTS_TARGETS["datascience"]

    def test_without_codes_by_category_falls_back_to_catalog_category(self, monkeypatch):
        monkeypatch.setattr(
            nodes,
            "get_catalog_courses",
            lambda: [_course("inf535", "datascience", 6, compulsory=False)],
        )
        targets = nodes._compute_remaining_targets(frozenset({"inf535"}))
        assert targets["datascience"] == nodes._CATEGORY_ECTS_TARGETS["datascience"] - 6
        assert targets["specialization"] == nodes._CATEGORY_ECTS_TARGETS["specialization"]


class TestExtractCompletedCodesByCategory:
    def test_absent_line_returns_empty_dict(self):
        assert nodes._extract_completed_codes_by_category("What should I take next semester?") == {}

    def test_present_line_is_parsed_into_category_buckets(self):
        text = (
            "Codes by category: economics: wir821, wir873; specialization: inf530, inf536, inf535\n"
            "What should I take next semester?"
        )
        result = nodes._extract_completed_codes_by_category(text)
        assert result == {
            "economics": frozenset({"wir821", "wir873"}),
            "specialization": frozenset({"inf530", "inf536", "inf535"}),
        }


class TestApplyTermPins:
    def test_compulsory_courses_are_moved_ahead_of_electives(self):
        courses = [
            _course("elec1", "economics", 6, compulsory=False),
            _course("comp1", "economics", 6, compulsory=True),
            _course("elec2", "empirical", 6, compulsory=False),
            _course("comp2", "empirical", 6, compulsory=True),
        ]
        result = nodes._apply_term_pins(courses)
        codes_in_order = [c["code"] for c in result]
        assert codes_in_order.index("comp1") < codes_in_order.index("elec1")
        assert codes_in_order.index("comp2") < codes_in_order.index("elec2")

    def test_explicit_pins_still_take_precedence_over_compulsory_sort(self):
        # wir895 is both compulsory and explicitly late-pinned - the late
        # pin (a deliberate, explicit scheduling choice) must still win over
        # the generic "compulsory first" rule.
        courses = [
            _course("wir895", "economics", 6, compulsory=True),
            _course("comp1", "economics", 6, compulsory=True),
            _course("wir894", "empirical", 6, compulsory=True),
        ]
        result = nodes._apply_term_pins(courses)
        codes_in_order = [c["code"] for c in result]
        assert codes_in_order[0] == "wir894"
        assert codes_in_order[-1] == "wir895"


class TestSelectRecommendedCourses:
    def test_excluded_codes_never_reappear(self, monkeypatch):
        catalog = [
            _course("wir821", "economics", 6, compulsory=True),
            _course("wir873", "economics", 6, compulsory=True),
            _course("mam", "thesis", 30, compulsory=True),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        exclude = frozenset({"wir821"})
        targets = nodes._compute_remaining_targets(exclude)
        selected = nodes._select_recommended_courses(exclude_codes=exclude, targets=targets)
        assert "wir821" not in {c["code"] for c in selected}
        assert "wir873" in {c["code"] for c in selected}

    def test_thesis_dropped_entirely_once_its_code_is_excluded(self, monkeypatch):
        catalog = [
            _course("wir821", "economics", 6, compulsory=True),
            _course("mam", "thesis", 30, compulsory=True),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        exclude = frozenset({"mam"})
        targets = nodes._compute_remaining_targets(exclude)
        selected = nodes._select_recommended_courses(exclude_codes=exclude, targets=targets)
        assert all(c["category"] != "thesis" for c in selected)

    def test_already_satisfied_elective_category_is_not_overfilled(self, monkeypatch):
        # Two electives worth 18 ECTS combined satisfy the "empirical" target
        # (18) on their own; with one already completed, only compulsory
        # courses plus enough electives to reach the *remaining* target
        # should be chosen - not the full original target again.
        catalog = [
            _course("emp1", "empirical", 9, compulsory=False, offering="WiSe"),
            _course("emp2", "empirical", 9, compulsory=False, offering="WiSe"),
            _course("emp3", "empirical", 9, compulsory=False, offering="WiSe"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        exclude = frozenset({"emp1"})
        targets = nodes._compute_remaining_targets(exclude)
        assert targets["empirical"] == 9
        selected = nodes._select_recommended_courses(exclude_codes=exclude, targets=targets)
        empirical_selected = [c for c in selected if c["category"] == "empirical"]
        assert sum(c["ects"] for c in empirical_selected) == 9
        assert "emp1" not in {c["code"] for c in empirical_selected}


class TestBuildProgressAwareScheduleAnswer:
    def test_with_exclude_codes_recommends_remaining_courses_not_thesis(self, monkeypatch):
        catalog = [
            _course("wir821", "economics", 6, compulsory=True, offering="WiSe"),
            _course("wir873", "economics", 6, compulsory=True, offering="WiSe"),
            _course("mam", "thesis", 30, compulsory=True),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        # wir821 already done, everything else (including the thesis) still
        # outstanding - a high completed_semesters value that would have
        # clamped straight to the thesis term under the old logic must not
        # matter once exclude_codes is supplied.
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next semester?",
            completed_semesters=99,
            exclude_codes=frozenset({"wir821"}),
        )
        assert answer is not None
        assert "wir873" in answer
        assert "Master" not in answer and "mam" not in answer.lower()

    def test_without_exclude_codes_behavior_is_unchanged(self, monkeypatch):
        catalog = [_course("wir821", "economics", 6, compulsory=True, offering="WiSe")]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next semester?", completed_semesters=0
        )
        assert answer is not None
        assert "wir821" in answer

    def test_cross_listed_elective_with_codes_by_category_does_not_overrecommend(self, monkeypatch):
        # Reproduces a real case: inf535 is catalogued as "datascience" here,
        # but the student's own tracker counts it toward "specialization" -
        # already fully covering that category. Without codes_by_category,
        # this used to wrongly compute 12 ECTS still owed in specialization
        # and recommend a superfluous elective; with it, nothing should be
        # recommended for a fully-satisfied programme except the thesis.
        catalog = [
            _course("inf535", "datascience", 6, compulsory=False, offering="WiSe"),
            _course("inf530", "specialization", 6, compulsory=False, offering="SoSe"),
            _course("inf536", "datascience", 6, compulsory=False, offering="SoSe"),
            _course("extra_specialization", "specialization", 6, compulsory=False, offering="WiSe"),
            _course("mam", "thesis", 30, compulsory=True),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        exclude = frozenset({"inf535", "inf530", "inf536"})
        codes_by_category = {"specialization": frozenset({"inf535", "inf530", "inf536"})}
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next semester?",
            completed_semesters=0,
            exclude_codes=exclude,
            codes_by_category=codes_by_category,
        )
        assert answer is not None
        assert "extra_specialization" not in answer.lower()
        assert "mam" in answer.lower()


class TestCurrentRealSemesterLabel:
    def test_during_sose_next_is_this_years_wise(self):
        assert nodes._current_real_semester_label(date(2026, 6, 15)) == "WiSe26/27"

    def test_early_in_wise_next_is_next_years_sose(self):
        assert nodes._current_real_semester_label(date(2026, 11, 1)) == "SoSe27"

    def test_start_of_year_still_in_wise_next_is_this_years_sose(self):
        assert nodes._current_real_semester_label(date(2027, 2, 1)) == "SoSe27"


class TestSemesterSortKey:
    def test_parses_wise_and_sose_labels(self):
        assert nodes._semester_sort_key("WiSe26/27") == (2026, 1)
        assert nodes._semester_sort_key("SoSe26") == (2026, 0)

    def test_sose_sorts_before_wise_in_the_same_year(self):
        assert nodes._semester_sort_key("SoSe26") < nodes._semester_sort_key("WiSe26/27")

    def test_malformed_label_returns_none(self):
        assert nodes._semester_sort_key("not a semester") is None


class TestIsConfirmedUnavailable:
    def test_real_gap_year_is_confirmed_unavailable(self):
        # Reproduces wir821's real catalog data: a SoSe-pattern course whose
        # history skips SoSe25 even though its data otherwise covers SoSe26.
        course = _course("wir821", "economics", 6, semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26")
        assert nodes._is_confirmed_unavailable(course, "SoSe25") is True

    def test_label_present_in_history_is_available(self):
        course = _course("wir821", "economics", 6, semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26")
        assert nodes._is_confirmed_unavailable(course, "SoSe26") is False

    def test_label_beyond_known_data_horizon_is_not_flagged(self):
        # The data only confirms up to SoSe26 - a term further out than that
        # is simply unknown yet, not a confirmed gap.
        course = _course("wir821", "economics", 6, semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26")
        assert nodes._is_confirmed_unavailable(course, "SoSe28") is False

    def test_extra_semesters_counts_as_confirmed_available(self):
        course = _course(
            "wir897", "empirical", 6,
            semesters_offered="SoSe25;WiSe26/27", extra_semesters="WiSe26/27;SoSe27",
        )
        assert nodes._is_confirmed_unavailable(course, "SoSe27") is False

    def test_course_with_no_offering_data_is_never_flagged(self):
        course = _course("wir888", "empirical", 6)
        assert nodes._is_confirmed_unavailable(course, "SoSe26") is False


class TestSelectRecommendedCoursesRealAvailability:
    def test_unavailable_elective_is_skipped_for_an_available_alternative(self, monkeypatch):
        catalog = [
            _course(
                "gapcourse", "specialization", 6, offering="SoSe",
                semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26",
            ),
            _course("altcourse", "specialization", 6, offering="SoSe", semesters_offered="SoSe25;SoSe26;SoSe27"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        substitutions: list[dict] = []
        # target covers both electives' combined ECTS, so the fill loop
        # always considers both regardless of their random shuffle order -
        # otherwise an early `total >= target` break could skip evaluating
        # gapcourse at all, making the substitution count nondeterministic.
        selected = nodes._select_recommended_courses(
            targets={"specialization": 12}, real_target_label="SoSe25", substitutions_out=substitutions
        )
        codes = {c["code"] for c in selected}
        assert "gapcourse" not in codes
        assert "altcourse" in codes
        assert len(substitutions) == 1
        assert substitutions[0]["course"]["code"] == "gapcourse"
        assert substitutions[0]["reason"] == "elective_skipped"

    def test_unavailable_compulsory_is_kept_but_flagged(self, monkeypatch):
        catalog = [
            _course(
                "mustcourse", "economics", 6, compulsory=True, offering="SoSe",
                semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26",
            ),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        substitutions: list[dict] = []
        selected = nodes._select_recommended_courses(
            targets={"economics": 6}, real_target_label="SoSe25", substitutions_out=substitutions
        )
        assert "mustcourse" in {c["code"] for c in selected}
        assert len(substitutions) == 1
        assert substitutions[0]["course"]["code"] == "mustcourse"
        assert substitutions[0]["reason"] == "compulsory_unconfirmed"

    def test_no_real_target_label_means_no_filtering(self, monkeypatch):
        catalog = [
            _course(
                "gapcourse", "specialization", 6, offering="SoSe",
                semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26",
            ),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        selected = nodes._select_recommended_courses(targets={"specialization": 6})
        assert "gapcourse" in {c["code"] for c in selected}


class TestBuildProgressAwareScheduleAnswerRealAvailability:
    def test_next_semester_answer_substitutes_and_notes_a_confirmed_gap(self, monkeypatch):
        catalog = [
            _course(
                "gapcourse", "specialization", 6, offering="SoSe",
                semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26",
            ),
            _course("altcourse", "specialization", 6, offering="SoSe", semesters_offered="SoSe25;SoSe26;SoSe27"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_real_semester_label", lambda: "SoSe25")
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next semester?", completed_semesters=0
        )
        assert answer is not None
        assert "altcourse" in answer
        assert "gapcourse" in answer  # named in the note, even though not recommended
        assert "isn't confirmed as offered next term" in answer

    def test_full_plan_request_is_not_filtered_by_real_availability(self, monkeypatch):
        # A multi-semester plan spans real years the catalog can't confirm
        # that far out, so it must not apply the real-target-label filter at
        # all - the course should appear normally, with no gap note.
        catalog = [
            _course(
                "gapcourse", "specialization", 6, offering="SoSe",
                semesters_offered="SoSe22;SoSe23;SoSe24;SoSe26",
            ),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_real_semester_label", lambda: "SoSe25")
        answer = nodes._build_progress_aware_schedule_answer(
            "Give me the full plan until graduation", completed_semesters=0
        )
        assert answer is not None
        assert "gapcourse" in answer
        assert "isn't confirmed as offered next term" not in answer


class TestDefaultSeasonMatchesRealCalendar:
    def test_unstated_season_defaults_to_the_real_upcoming_one_not_always_wise(self, monkeypatch):
        # Before this fix, no explicit season in the question always fell
        # back to a hardcoded "WiSe" regardless of the real time of year -
        # wrong whenever asked during WiSe, when the real next term is SoSe.
        catalog = [
            _course("wisecourse", "specialization", 6, offering="WiSe"),
            _course("sosecourse", "specialization", 6, offering="SoSe"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_real_semester_label", lambda: "SoSe27")
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next semester?", completed_semesters=0
        )
        assert answer is not None
        assert "(SoSe)" in answer
        assert "sosecourse" in answer

    def test_explicit_season_in_the_question_still_overrides_the_default(self, monkeypatch):
        catalog = [
            _course("wisecourse", "specialization", 6, offering="WiSe"),
            _course("sosecourse", "specialization", 6, offering="SoSe"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_real_semester_label", lambda: "SoSe27")
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next WiSe semester?", completed_semesters=0
        )
        assert answer is not None
        assert "(WiSe)" in answer
        assert "wisecourse" in answer


class TestCurrentSemesterRequest:
    def test_looks_like_current_semester_request_detects_this_semester_phrasing(self):
        assert nodes._looks_like_current_semester_request("Which courses should I take this semester?")
        assert nodes._looks_like_current_semester_request("What's offered currently?") is False
        assert nodes._looks_like_current_semester_request("What should I take this term?")

    def test_default_next_semester_question_is_not_treated_as_current(self):
        assert nodes._looks_like_current_semester_request("What should I take next semester?") is False

    def test_current_running_semester_label_during_wise(self):
        assert nodes._current_running_semester_label(date(2026, 11, 1)) == "WiSe26/27"
        assert nodes._current_running_semester_label(date(2027, 2, 1)) == "WiSe26/27"

    def test_current_running_semester_label_during_sose(self):
        assert nodes._current_running_semester_label(date(2026, 6, 15)) == "SoSe26"

    def test_this_semester_answer_is_labelled_this_not_next(self, monkeypatch):
        catalog = [_course("wisecourse", "specialization", 6, offering="WiSe")]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_running_semester_label", lambda: "WiSe26/27")
        answer = nodes._build_progress_aware_schedule_answer(
            "Which courses should I take this semester?", completed_semesters=0
        )
        assert answer is not None
        assert "this semester" in answer.lower()
        assert "next semester" not in answer.lower()
        assert "wisecourse" in answer

    def test_this_semester_uses_the_running_not_the_upcoming_term(self, monkeypatch):
        # During WiSe, "this semester" must anchor to the WiSe courses, not
        # the upcoming SoSe that "next semester" would use.
        catalog = [
            _course("wisecourse", "specialization", 6, offering="WiSe"),
            _course("sosecourse", "specialization", 6, offering="SoSe"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_running_semester_label", lambda: "WiSe26/27")
        monkeypatch.setattr(nodes, "_current_real_semester_label", lambda: "SoSe27")
        answer = nodes._build_progress_aware_schedule_answer(
            "Which courses should I take this semester?", completed_semesters=0
        )
        assert answer is not None
        assert "wisecourse" in answer
        assert "sosecourse" not in answer

    def test_retrieve_node_skips_the_clarifying_question_for_this_semester(self, monkeypatch):
        catalog = [_course("wisecourse", "specialization", 6, offering="WiSe")]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        monkeypatch.setattr(nodes, "_current_running_semester_label", lambda: "WiSe26/27")

        class FakeMessage:
            def __init__(self, content):
                self.content = content

        state = {"messages": [FakeMessage("Which courses should I take this semester?")]}
        result = nodes.retrieve_node(state)
        assert result["awaiting_semester_number"] is False
        assert result["direct_answer"] is not None
        assert "wisecourse" in result["direct_answer"]

    def test_retrieve_node_skips_the_clarifying_question_for_full_plan(self, monkeypatch):
        catalog = [
            _course("wisecourse", "economics", 6, compulsory=True, offering="WiSe"),
            _course("mam", "thesis", 30, compulsory=True),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)

        class FakeMessage:
            def __init__(self, content):
                self.content = content

        state = {
            "messages": [
                FakeMessage("Can you make a schedule for the full programme, all the way until graduation?")
            ]
        }
        result = nodes.retrieve_node(state)
        assert result["awaiting_semester_number"] is False
        assert result["direct_answer"] is not None
        assert "Semester" in result["direct_answer"]


class TestDifficultyAwareSelection:
    def test_easier_elective_is_preferred_when_only_one_is_needed(self, monkeypatch):
        catalog = [
            _course("hard", "specialization", 6, offering="WiSe", difficulty_avg=4.8, difficulty_count=5),
            _course("easy", "specialization", 6, offering="WiSe", difficulty_avg=1.2, difficulty_count=5),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        # Run several times - the shuffle happens before the difficulty
        # sort, so this must hold regardless of shuffle order, not just by
        # chance once.
        for _ in range(10):
            selected = nodes._select_recommended_courses(targets={"specialization": 6})
            assert {c["code"] for c in selected} == {"easy"}

    def test_unrated_courses_still_vary_between_requests(self, monkeypatch):
        # Neither course has a rating, so the neutral 3.0 key ties them -
        # the pre-sort shuffle should still let either one come up.
        catalog = [
            _course("a", "specialization", 6, offering="WiSe"),
            _course("b", "specialization", 6, offering="WiSe"),
        ]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        seen = {
            tuple(c["code"] for c in nodes._select_recommended_courses(targets={"specialization": 6}))
            for _ in range(20)
        }
        assert seen == {("a",), ("b",)}

    def test_difficulty_is_shown_in_the_formatted_answer(self, monkeypatch):
        catalog = [_course("rated", "specialization", 6, offering="WiSe", difficulty_avg=2.3, difficulty_count=4)]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next WiSe semester?", completed_semesters=0
        )
        assert answer is not None
        assert "difficulty 2.3/5 (4 votes)" in answer

    def test_unrated_course_shows_no_difficulty_text(self, monkeypatch):
        catalog = [_course("unrated", "specialization", 6, offering="WiSe")]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next WiSe semester?", completed_semesters=0
        )
        assert answer is not None
        assert "difficulty" not in answer.lower()

    def test_single_vote_uses_singular_word(self, monkeypatch):
        catalog = [_course("rated", "specialization", 6, offering="WiSe", difficulty_avg=3.0, difficulty_count=1)]
        monkeypatch.setattr(nodes, "get_catalog_courses", lambda: catalog)
        answer = nodes._build_progress_aware_schedule_answer(
            "What should I take next WiSe semester?", completed_semesters=0
        )
        assert answer is not None
        assert "1 vote)" in answer
        assert "1 votes)" not in answer


class TestFlexibleHintMatching:
    def test_a_word_inserted_into_a_hint_phrase_still_matches(self):
        # Reproduces a real failure: "make a schedule" (a listed hint)
        # didn't match "make a FULL schedule" under the old exact-substring
        # check, so the whole deterministic schedule-builder path was
        # silently skipped in favor of a free-form LLM answer.
        assert nodes._looks_like_schedule_request("Can you make a full schedule until graduation?")
        assert nodes._looks_like_full_plan_request("Can you make a full schedule until graduation?")

    def test_exact_hint_phrases_still_match_unchanged(self):
        assert nodes._looks_like_schedule_request("What should I take next semester?")
        assert nodes._looks_like_schedule_request("Can you recommend courses for me?")
        assert nodes._looks_like_full_plan_request("Give me the full plan.")
        assert nodes._looks_like_current_semester_request("Which courses should I take this semester?")

    def test_unrelated_text_does_not_match(self):
        assert nodes._looks_like_schedule_request("What is the weather like today?") is False
        assert nodes._looks_like_schedule_request("Can you recommend a good restaurant for dinner?") is False

    def test_gap_tolerance_is_bounded_not_a_free_fuzzy_match(self):
        # More than one inserted word between the hint's own words must not
        # match - this is deliberately tight, not a general fuzzy matcher.
        # (Avoids any other listed hint, like "schedule for" or "plan for",
        # appearing elsewhere in the sentence - this is specifically about
        # "make a plan"'s own internal gap.)
        assert nodes._looks_like_schedule_request("Can you make me a really quite elaborate plan?") is False
