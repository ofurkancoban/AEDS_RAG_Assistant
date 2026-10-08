"""graph.nodes._translate_to_english: the corpus and its embedding
model are English-only on purpose (see README), so a German question is
translated before hybrid_search/rerank rather than embedded as-is. Retrieval
quality on English questions - the majority case - must stay untouched:
_looks_german's whole job is making sure English text never reaches the
translation call at all."""

import pytest

from graph import nodes


class _FakeTranslation:
    def __init__(self, content):
        self.content = content


@pytest.mark.parametrize(
    "text",
    [
        "Wann ist die Bewerbungsfrist für EU-Bewerber?",
        "Welche Kurse sind Pflichtkurse?",
        "Wie viele ECTS braucht man insgesamt?",
        "Müssen wir uns zurückmelden?",
        "Ich möchte wissen, ob es Sprachvoraussetzungen gibt.",
    ],
)
def test_looks_german_catches_real_german_questions(text):
    assert nodes._looks_german(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "What is the application deadline?",
        "Which courses are compulsory?",
        "How many ECTS do I need in total?",
        "What was the deadline for non-EU applicants?",
        "Is there a thesis requirement?",
    ],
)
def test_looks_german_does_not_fire_on_english_questions(text):
    assert nodes._looks_german(text) is False


def test_an_english_query_is_never_sent_for_translation(monkeypatch):
    def _fail_if_called():
        raise AssertionError("get_classifier_llm() must not be called for an English query")

    monkeypatch.setattr(nodes, "get_classifier_llm", _fail_if_called)

    result = nodes._translate_to_english("What is the application deadline?")

    assert result == "What is the application deadline?"


def test_a_german_query_is_translated_before_retrieval(monkeypatch):
    monkeypatch.setattr(nodes, "get_classifier_llm", lambda: object())
    monkeypatch.setattr(nodes, "_with_fallback", lambda llm, tools=None: llm)
    monkeypatch.setattr(
        nodes, "_with_resilience",
        lambda llm, **kw: type("Stub", (), {"invoke": lambda self, prompt: _FakeTranslation("What is the application deadline?")})(),
    )

    result = nodes._translate_to_english("Wann ist die Bewerbungsfrist?")

    assert result == "What is the application deadline?"


def test_a_failed_translation_falls_back_to_the_original_query(monkeypatch):
    def _raise(llm, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(nodes, "get_classifier_llm", lambda: object())
    monkeypatch.setattr(nodes, "_with_fallback", lambda llm, tools=None: llm)
    monkeypatch.setattr(nodes, "_with_resilience", _raise)

    original = "Wann ist die Bewerbungsfrist?"
    result = nodes._translate_to_english(original)

    assert result == original
