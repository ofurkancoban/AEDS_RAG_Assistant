"""Lightweight keyword-based topic tagging for chunks.

This intentionally avoids an LLM call per chunk (would be slow across hundreds
of chunks on a local model) in favor of a fast heuristic classifier. Tags are
attached as chunk metadata so retrieval can later filter or boost by topic.
"""

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "admission": [
        "admission requirement", "entry qualification", "bachelor's degree",
        "bachelor’s degree", "credit points", "ects credits", "cefr", "level b2",
        "language proficiency", "prerequisite for admission",
    ],
    "deadline": [
        "deadline", "first day of application", "application window",
        "winter semester", "summer semester", "15 july", "15 june", "15 march",
        "15 may", "march 15", "may 15", "june 15", "july 15",
    ],
    "curriculum": [
        "module", "curriculum", " cp ", "credit point", "compulsory", "elective",
        "specialisation", "specialization", "lecture", "seminar",
    ],
    "career": [
        "career", "employer", "graduates", "job market", "profession",
    ],
    "fees": [
        "tuition", "fee", "semester contribution",
    ],
    "exams": [
        "examination", "exam regulation", "prüfungsordnung", "thesis", "colloquium",
    ],
    "contact": [
        "counselling", "advisor", "contact", "@uol.de", "phone",
    ],
}


def classify_topics(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    matched = [topic for topic, keywords in TOPIC_KEYWORDS.items() if any(kw in lowered for kw in keywords)]
    return matched or ["general"]
