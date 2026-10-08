"""Find documents that state different values for the same fact.

Two wrong answers in one week came from documents disagreeing with each
other: an English translation of the examination regulations said thesis
admission needs "2 ECTS" (the binding German text: 60), and a university-
wide thesis FAQ gave "about eight weeks" for grading where this programme's
regulations say six. Neither is visible from any single document.

Each FACT below is a set of patterns that capture one value. Every document
(Markdown as written, PDFs as extracted text) is searched; a fact whose
documents give more than one distinct value is reported, with the file and
the sentence each value came from. Weekly from scripts/maintenance.py, with
a Telegram summary when something is found.

Usage:
    python scripts/check_contradictions.py            # print the report
    python scripts/check_contradictions.py --notify   # also send it to Telegram
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

# name -> patterns; group 1 is the value. Values are compared after
# normalize(), so "six weeks" and "6 weeks" are the same value.
FACTS: dict[str, list[str]] = {
    "thesis grading time (weeks)": [
        r"(?:thesis|Master.s thesis)[^.]{0,120}?(?:assess|grad)\w*[^.]{0,60}?within (?:about )?(\w+) weeks",
        r"(?:assessment|grading)[^.]{0,80}?thesis[^.]{0,60}?within (?:about )?(\w+) weeks",
        # The thesis FAQ names the topic in its heading, not in the sentence.
        r"[Hh]ow long does grading take[^?]{0,80}\?[^#]{0,250}?within (?:about )?(\w+) weeks",
    ],
    "thesis writing period (months)": [
        r"(\w+) months (?:in which )?to (?:complete|write) the (?:Master.s )?thesis",
        r"students have (\w+) months to complete the Master.s thesis",
    ],
    "thesis admission (ECTS)": [
        r"admission to the Master.s thesis[^.]{0,400}?at least (\d+) (?:ECTS|credit)",
        r"admitted to the Master.s thesis[^.]{0,400}?at least (\d+) (?:ECTS|credit)",
    ],
    "thesis module credits": [
        r"(\d+) credit points are awarded for the final Master.s module",
        r"final Master.s module[^.]{0,40}?is worth (\d+) credit points",
        r"thesis module[^.]{0,40}?(?:is worth|carries|awards?) (\d+) (?:ECTS|credit)",
    ],
    "thesis length (characters)": [
        r"Master.s thesis should not exceed ([\d,. ]+) characters",
    ],
    "seminar paper length (characters)": [
        r"seminar paper[^.]{0,120}?between ([\d,. ]+) and [\d,. ]+ characters",
        r"text should be between ([\d,. ]+) and [\d,. ]+ characters",
    ],
    "resits of a failed module exam": [
        r"[Ff]ailed module examinations can be retaken (\w+)",
        r"retake a failed module (?:exam|examination)[^.]{0,40}?(\w+) times",
    ],
    "total programme credits": [
        r"workload of (\d+) credit points",
        r"programme (?:has|comprises|is worth) (?:a total of )?(\d+) (?:ECTS|credit points)",
    ],
    "semester contribution, regular students (EUR)": [
        r"[Rr]egular students[^.]{0,80}?pay EUR ([\d.,]+)",
    ],
    "English level required": [
        r"English (?:at level|language proficiency[^.]{0,40}?level) (B2|C1|B1)",
        r"requires English at level (B2|C1|B1)",
    ],
}

_WORDS = {"one": "1", "once": "1", "two": "2", "twice": "2", "three": "3", "four": "4", "five": "5",
          "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def normalize(value: str) -> str:
    v = value.strip().lower().rstrip(".,")
    v = _WORDS.get(v, v)
    if re.fullmatch(r"[\d.,\s]+", v):
        v = re.sub(r"[.,\s]", "", v)
    return v


def _documents() -> dict[str, str]:
    texts = {}
    for path in sorted(settings.documents_dir.iterdir()):
        if path.suffix.lower() == ".md":
            texts[path.name] = path.read_text(encoding="utf-8")
        elif path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            texts[path.name] = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return {name: " ".join(text.split()) for name, text in texts.items()}


def find_conflicts(texts: dict[str, str]) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """fact -> value -> [(document, sentence)] for facts with 2+ values."""
    conflicts = {}
    for fact, patterns in FACTS.items():
        values: dict[str, list[tuple[str, str]]] = {}
        for name, text in texts.items():
            for pattern in patterns:
                for m in re.finditer(pattern, text):
                    start = max(0, m.start() - 40)
                    snippet = text[start : m.end() + 20]
                    values.setdefault(normalize(m.group(1)), []).append((name, snippet))
        if len(values) > 1:
            conflicts[fact] = values
    return conflicts


def report(conflicts) -> str:
    if not conflicts:
        return "No contradictions found between documents."
    lines = [f"Documents disagree on {len(conflicts)} fact(s):"]
    for fact, values in conflicts.items():
        lines.append(f"\n{fact}:")
        for value, places in values.items():
            files = sorted({name for name, _ in places})
            lines.append(f"  {value!r} in {', '.join(files)}")
            lines.append(f"     \"...{places[0][1]}...\"")
    return "\n".join(lines)


def main() -> int:
    conflicts = find_conflicts(_documents())
    text = report(conflicts)
    print(text)
    if conflicts and "--notify" in sys.argv:
        from api.telegram_bot import _notify_admins

        _notify_admins("Document contradiction check\n" + text[:3500])
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
