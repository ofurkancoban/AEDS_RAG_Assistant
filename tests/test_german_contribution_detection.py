"""detect_contribution_node: a German correction/new-fact message must reach
the same could_be_a_contribution (Laya) gate an equivalent English one would,
translated first - db/contribution_gate.py's multilingual checkpoint measured
much weaker than its English one on this task (see graph.nodes._translate_to_english)."""

from langchain_core.messages import AIMessage, HumanMessage

from graph import nodes


def _state_for(message_text: str) -> dict:
    return {
        "messages": [
            HumanMessage(content="irrelevant prior turn"),
            HumanMessage(content=message_text),
            AIMessage(content="prior answer, present only so index -2 is the human turn"),
        ]
    }


def test_a_german_correction_is_translated_before_the_gate(monkeypatch):
    gate_calls = []
    monkeypatch.setattr(nodes, "could_be_a_contribution", lambda text: gate_calls.append(text) or False)
    monkeypatch.setattr(nodes, "_translate_to_english", lambda text: "Actually the deadline is July 15th, not July 1st.")

    state = _state_for("Eigentlich ist die Frist der 15. Juli, nicht der 1. Juli.")
    result = nodes.detect_contribution_node(state)

    # The gate saw the translated English text, not the raw German.
    assert gate_calls == ["Actually the deadline is July 15th, not July 1st."]
    assert result == {"detected_contribution": None}


def test_an_english_correction_still_reaches_the_gate_unchanged(monkeypatch):
    gate_calls = []
    monkeypatch.setattr(nodes, "could_be_a_contribution", lambda text: gate_calls.append(text) or False)
    # _translate_to_english itself is real here (not stubbed) - an English
    # message must pass through it as a no-op, same as retrieval's query.
    state = _state_for("Actually the deadline is July 15th, not July 1st.")

    nodes.detect_contribution_node(state)

    assert gate_calls == ["Actually the deadline is July 15th, not July 1st."]


def test_the_extraction_prompt_still_sees_the_original_german_text(monkeypatch):
    monkeypatch.setattr(nodes, "could_be_a_contribution", lambda text: True)
    monkeypatch.setattr(nodes, "_translate_to_english", lambda text: "Actually the deadline is July 15th, not July 1st.")

    captured_prompts = []

    class _FakeResponse:
        content = '{"is_contribution": true, "type": "correction", "content": "The deadline is July 15th."}'

    class _FakeLLM:
        def invoke(self, prompt):
            captured_prompts.append(prompt)
            return _FakeResponse()

    monkeypatch.setattr(nodes, "_with_resilience", lambda llm, **kw: llm)
    monkeypatch.setattr(nodes, "_with_fallback", lambda llm, tools=None: llm)
    monkeypatch.setattr(nodes, "get_classifier_llm", lambda: _FakeLLM())

    original = "Eigentlich ist die Frist der 15. Juli, nicht der 1. Juli."
    state = _state_for(original)

    nodes.detect_contribution_node(state)

    assert len(captured_prompts) == 1
    assert original in captured_prompts[0]
