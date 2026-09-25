"""Reads the Examining Board chair / Examinations Office contact fact back out
of AEDS_website_exams_regulations.md, once ingested - parsed fresh from
whatever is currently ingested (like ingestion/catalog.py and
ingestion/deadlines.py do), rather than hardcoded, so it stays in sync if the
source document is ever updated."""

import re

from db.chroma_client import get_all_rows_for_source

EXAMS_REGULATIONS_SOURCE_ID = "AEDS_website_exams_regulations"

# Matches on name shape (optional "Prof."/"Dr." prefixes, then capitalized
# words) rather than stopping at the next period - a plain "stop at the next
# '.'" pattern breaks on abbreviation periods inside the title itself (e.g.
# "Prof. Dr. Emmanuel Asane-Otoo" ends the match after "Prof").
_CHAIR_RE = re.compile(
    r"chair of the Examining Board for this programme is\s+"
    r"((?:Prof\.\s*)?(?:Dr\.\s*)?[A-ZÀ-Ý][\wÀ-ÿ'-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'-]*)+)",
)


def get_examining_board_chair() -> str | None:
    rows = get_all_rows_for_source(EXAMS_REGULATIONS_SOURCE_ID)
    # Normalize whitespace (the source text can wrap a name across a line
    # break) so a name spanning a newline still matches as one contiguous name.
    text = " ".join(" ".join(row.page_content.split()) for row in rows)
    match = _CHAIR_RE.search(text)
    return match.group(1).strip() if match else None
