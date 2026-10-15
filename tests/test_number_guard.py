"""An answer that states a figure missing from its context is caught, and
the guard asks once more without streaming the second attempt."""

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from config import settings
from graph import nodes

CONTEXT = (
    "International students may work 140 full days or 280 half days per year. Proof of EUR 11,904 "
    "per year (12 x EUR 992). Contribution EUR 457.90. Office hours 10:00-14:00. Deadline July 15 2026."
)


@pytest.mark.parametrize("answer, unsupported", [
    ("Sie dürfen 140 Vollarbeitstage oder 200 Halbtage arbeiten [1].", ["200"]),
    ("Sie dürfen 140 volle Tage oder 280 halbe Tage arbeiten [1][2].", []),
    ("Finanzierung: 11.904 € pro Jahr (992 € monatlich), Beitrag 457,90 €.", []),
    ("Office hours 10:00-14:00; module wir874; steps 1. and 2.", []),
    ("The deadline is July 15, 2026.", []),
    ("You need 120 ECTS in total.", ["120"]),
    ("140 full days plus 280 half days make 420 entries.", []),
    ("Sie dürfen 140 Tage, also 200 Halbtage arbeiten.", ["200"]),
])
def test_unsupported_figures_are_found(answer, unsupported):
    assert nodes.unsupported_numbers(answer, CONTEXT) == unsupported


def _generate(monkeypatch, answers, mode="regenerate"):
    calls = []

    class Llm:
        def invoke(self, messages, config=None):
            calls.append(config)
            return AIMessage(content=answers[len(calls) - 1])

    monkeypatch.setattr(settings, "number_guard", mode)
    monkeypatch.setattr(nodes, "get_llm", lambda: Llm())
    monkeypatch.setattr(nodes, "_with_resilience", lambda llm, **kw: llm)
    monkeypatch.setattr(nodes, "_with_fallback", lambda llm, **kw: llm)
    monkeypatch.setattr(nodes, "get_expired_source_ids", lambda: {})
    docs = [Document(page_content=CONTEXT, metadata={"source_id": "work"})]
    out = nodes.generate_node({"retrieved_docs": docs, "messages": [HumanMessage(content="Wie viel darf ich arbeiten?")]})
    return out["messages"][0].content, calls


def test_a_wrong_figure_is_regenerated_without_streaming(monkeypatch):
    answer, calls = _generate(monkeypatch, ["Sie dürfen 200 Halbtage arbeiten [1].", "Sie dürfen 280 Halbtage arbeiten [1]."])
    assert answer == "Sie dürfen 280 Halbtage arbeiten [1]."
    assert len(calls) == 2 and calls[1] == {"callbacks": []}


def test_a_retry_that_is_no_better_keeps_the_first_answer(monkeypatch):
    answer, calls = _generate(monkeypatch, ["Sie dürfen 200 Halbtage arbeiten [1].", "Sie dürfen 300 Halbtage arbeiten [1]."])
    assert answer == "Sie dürfen 200 Halbtage arbeiten [1]."


def test_log_mode_does_not_call_the_model_again(monkeypatch):
    answer, calls = _generate(monkeypatch, ["Sie dürfen 200 Halbtage arbeiten [1]."], mode="log")
    assert len(calls) == 1


def test_a_supported_answer_costs_one_call(monkeypatch):
    answer, calls = _generate(monkeypatch, ["Sie dürfen 280 Halbtage arbeiten [1]."])
    assert len(calls) == 1


_SEMINAR_CONTEXT = (
    "[1] The seminar paper should be between 30,000 and 45,000 characters. "
    "Modules are worth 6 or 20 ECTS. Fee EUR 457.90."
)


def test_a_figure_with_a_unit_the_context_never_gives_it_is_flagged():
    found = nodes.unsupported_numbers("Eine Hausarbeit sollte etwa 15–20 Seiten lang sein [1].", _SEMINAR_CONTEXT)
    assert "15" in found
    assert any(f.startswith("20 (pages") for f in found)


def test_units_match_across_english_and_german():
    assert nodes.unsupported_numbers("Die Hausarbeit umfasst 30.000 bis 45.000 Zeichen.", _SEMINAR_CONTEXT) == []
    assert nodes.unsupported_numbers("Sie zahlen 457,90 € pro Semester.", _SEMINAR_CONTEXT) == []
    assert nodes.unsupported_numbers("The module gives 20 credit points.", _SEMINAR_CONTEXT) == []


def test_a_figure_the_context_also_gives_without_a_unit_is_accepted():
    # A table cell has no unit; that is ambiguous, not a contradiction.
    assert nodes.unsupported_numbers("It takes 20 weeks.", "| Module | 20 | 6 |") == []


def test_the_system_prompt_is_not_evidence():
    # "15" occurs in the system prompt's own examples; only the context counts.
    assert "15" in str(nodes.SYSTEM_PROMPT)
    assert nodes.unsupported_numbers("About 15 pages.", "[1] No length is given.") == ["15"]
