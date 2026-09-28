"""Parses CHANGELOG.md into structured entries for the /version API and the
frontend's version badge + changelog popup.

CHANGELOG.md (Keep a Changelog format) is the single source of truth for the
app's current version - the topmost entry's version number - rather than a
separate VERSION file or a hardcoded constant that could drift out of sync
with what the changelog actually documents.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import settings

CHANGELOG_PATH = settings.base_dir / "CHANGELOG.md"

_VERSION_HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$")
_SECTION_HEADING = re.compile(r"^### (?P<section>.+)$")


def parse_changelog(text: str) -> list[dict]:
    entries: list[dict] = []
    current_entry: dict | None = None
    current_section: str | None = None

    for line in text.splitlines():
        version_match = _VERSION_HEADING.match(line)
        if version_match:
            current_entry = {
                "version": version_match["version"],
                "date": version_match["date"],
                "sections": {},
            }
            entries.append(current_entry)
            current_section = None
            continue

        if current_entry is None:
            continue

        section_match = _SECTION_HEADING.match(line)
        if section_match:
            current_section = section_match["section"]
            current_entry["sections"].setdefault(current_section, [])
            continue

        stripped = line.strip()
        if not stripped or current_section is None:
            continue
        if stripped.startswith("- "):
            current_entry["sections"][current_section].append(stripped[2:])
        else:
            # A wrapped continuation of the previous bullet (Keep a Changelog
            # entries read better in the raw file wrapped at ~80 columns than
            # as one long line) - joined back onto it rather than dropped, or
            # kept as its own bogus list item.
            items = current_entry["sections"][current_section]
            if items:
                items[-1] = f"{items[-1]} {stripped}"

    return entries


def read_changelog(path: Path = CHANGELOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    return parse_changelog(path.read_text(encoding="utf-8"))


def current_version() -> str:
    entries = read_changelog()
    return entries[0]["version"] if entries else "0.0.0"
