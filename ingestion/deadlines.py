"""Reads the application deadlines table (AEDS_website_application_deadlines_table.md)
back out as plain Python data - queried from the Deadline SQL table (see
db.models.Deadline), which ingestion/structured_sync.py keeps in sync with the
source file every time it's (re-)ingested, rather than hardcoded or re-parsed
out of embedded Chroma chunk text on every call."""

from datetime import date, datetime

from db.models import Deadline, SessionLocal

_HEADER_CELLS = {"entry qualification", ""}

# The source table writes dates as "July 15, 2026".
_DATE_FORMAT = "%B %d, %Y"


def parse_deadline_date(value: str) -> date | None:
    """Parse a table date cell, or None if it isn't in the expected format -
    the table is scraped, so an unexpected cell should degrade to omitting the
    countdown rather than breaking the whole answer."""
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None


def _describe_days(count: int) -> str:
    return "1 day" if count == 1 else f"{count} days"


# A question can ask about several qualifications at once, producing one status
# sentence per deadline. The follow-up advice applies to all of them equally,
# so it is appended once by the caller (see graph/nodes.py's _route_with_tools)
# instead of being repeated inside every sentence.
DEADLINE_PASSED_MARKER = "has already passed"

NEXT_INTAKE_NOTE = (
    "Application dates are published separately for each intake, so check the programme "
    "website for the next cycle's dates."
)


def describe_deadline_status(first_day: str, deadline: str, today: date | None = None) -> str:
    """Render today's position relative to an application window as a sentence.

    Computed here rather than left to the model on purpose: the LLM has no
    reliable notion of the current date and has repeatedly gotten plain
    arithmetic wrong elsewhere in this project, while "is this deadline still
    open" is precisely the part a prospective applicant acts on. Returns an
    empty string when either date can't be parsed.
    """
    today = today or date.today()
    opens = parse_deadline_date(first_day)
    closes = parse_deadline_date(deadline)
    if closes is None:
        return ""

    if today > closes:
        return (
            f"This deadline {DEADLINE_PASSED_MARKER} - it was "
            f"{_describe_days((today - closes).days)} ago, so this application cycle is closed."
        )
    if today == closes:
        return "Today is the final day to apply - the deadline closes at the end of today."

    remaining = _describe_days((closes - today).days)
    if opens is not None and today < opens:
        return (
            f"Applications have not opened yet: the window opens in {_describe_days((opens - today).days)}, "
            f"and there are {remaining} until the deadline."
        )
    return f"Applications are open now, with {remaining} left until the deadline."


def parse_table_rows(text: str) -> list[list[str]]:
    """Parses a markdown pipe-table's data rows (skipping the header and the
    '|---|---|---|---|' separator) into raw [entry_qualification,
    starting_semester, first_day, deadline] cell lists. Shared with
    ingestion/structured_sync.py, which is the only other place this format is
    parsed."""
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 4:
            continue
        if cells[0].lower() in _HEADER_CELLS or set(cells[0]) <= {"-"}:
            continue  # header row or "|---|---|---|---|" separator
        rows.append(cells)
    return rows


def get_application_deadlines() -> dict[str, tuple[str, str]]:
    """Maps entry qualification (e.g. "Germany", "EU/EEA", "Non-EU (third
    countries)") to (first day of application, application deadline). In the
    source table, the "Higher Semester" row for a qualification is always a
    duplicate of that qualification's "First Semester" row - starting semester
    doesn't change either date - so only the first row seen per qualification
    is kept."""
    session = SessionLocal()
    try:
        deadlines: dict[str, tuple[str, str]] = {}
        for row in session.query(Deadline).all():
            deadlines.setdefault(row.entry_qualification, (row.first_day, row.deadline))
        return deadlines
    finally:
        session.close()
