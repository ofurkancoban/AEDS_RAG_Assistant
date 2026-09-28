"""changelog.py's parser and the public /version endpoint it backs."""

from changelog import parse_changelog

_SAMPLE = """# Changelog

## [1.2.0] - 2026-09-28
### Added
- Thing one
- Thing two
### Fixed
- Bug one

## [1.0.0] - 2026-09-25
### Added
- Initial release
"""


def test_parses_every_version_in_order():
    entries = parse_changelog(_SAMPLE)
    assert [e["version"] for e in entries] == ["1.2.0", "1.0.0"]


def test_parses_dates_and_sections():
    entries = parse_changelog(_SAMPLE)
    latest = entries[0]
    assert latest["date"] == "2026-09-28"
    assert latest["sections"]["Added"] == ["Thing one", "Thing two"]
    assert latest["sections"]["Fixed"] == ["Bug one"]


def test_text_before_the_first_version_heading_is_ignored():
    entries = parse_changelog("Some preamble\nnot a version line\n" + _SAMPLE)
    assert len(entries) == 2


def test_empty_changelog_parses_to_no_entries():
    assert parse_changelog("") == []


def test_a_wrapped_bullet_is_joined_back_into_one_item():
    text = (
        "## [1.0.0] - 2026-09-25\n"
        "### Added\n"
        "- A sentence that got wrapped across\n"
        "  two lines in the raw file.\n"
        "- A second, unrelated bullet.\n"
    )
    entries = parse_changelog(text)
    assert entries[0]["sections"]["Added"] == [
        "A sentence that got wrapped across two lines in the raw file.",
        "A second, unrelated bullet.",
    ]


def test_version_endpoint_reports_the_topmost_entry(client):
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == body["changelog"][0]["version"]
    assert len(body["changelog"]) >= 1
