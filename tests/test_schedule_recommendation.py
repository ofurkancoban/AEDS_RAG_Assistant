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

import pytest

from graph import nodes


def _course(code, category, ects, compulsory=False, offering=None, name=None):
    return {
        "code": code,
        "category": category,
        "ects": ects,
        "compulsory": compulsory,
        "offering": offering,
        "name": name or code,
        "professor": "",
        "language": "en",
    }


class TestExtractCompletedCodes:
    def test_absent_line_returns_empty_set(self):
        assert nodes._extract_completed_codes("What should I take next semester?") == frozenset()

    def test_present_line_is_parsed_lowercased_and_deduplicated(self):
        text = (
            "My ECTS Tracker progress (12/120 ECTS completed):\n"
            "Economics (12/36 ECTS) - completed: wir821 - Advanced Microeconomics\n"
            "Codes already completed, in progress, or planned: WIR821, wir873, wir821\n"
            "What should I take next semester?"
        )
        assert nodes._extract_completed_codes(text) == frozenset({"wir821", "wir873"})

    def test_malformed_line_with_no_codes_returns_empty_set(self):
        text = "Codes already completed, in progress, or planned: \nWhat should I take next?"
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
