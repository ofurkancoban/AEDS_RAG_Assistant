"""api/telegram_bot.py's plain-text formatting helpers: Telegram gets a
sendMessage with no parse_mode (see send_message's docstring), so any
markdown in the source text needs to be dealt with before it goes out,
not rendered."""

from api.telegram_bot import _flatten_headings, _strip_markdown, _truncate


def test_strip_markdown_removes_headers_bold_and_code():
    text = "# Title\n\nSome **bold** and `code`."
    assert _strip_markdown(text) == "Title\n\nSome bold and code."


def test_strip_markdown_alone_merges_a_heading_into_the_prose():
    # The known limitation _flatten_headings exists to fix for
    # notify_source_draft specifically - documented here so a future
    # change to _strip_markdown's own behavior doesn't silently reintroduce
    # it there without the test noticing.
    text = "## Section\nBody line."
    assert _strip_markdown(text) == "Section\nBody line."


def test_flatten_headings_gives_each_heading_a_visible_marker():
    text = "# Title\nIntro.\n\n## Section one\nBody one.\n\n### Section two\nBody two."

    result = _truncate(_flatten_headings(text))

    assert "▸ Title" in result
    assert "▸ Section one" in result
    assert "▸ Section two" in result
    # No literal markdown syntax left for a plain-text sendMessage to
    # show as stray characters.
    assert "#" not in result


def test_flatten_headings_does_not_pile_up_blank_lines():
    text = "# A\n\n## B\nbody"

    result = _flatten_headings(text)

    assert "\n\n\n" not in result


def test_flatten_headings_is_a_no_op_on_text_with_no_headings():
    text = "Just an ordinary sentence with no markdown structure."
    assert _flatten_headings(text) == text
