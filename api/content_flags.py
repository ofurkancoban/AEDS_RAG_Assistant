"""Spotting text that is addressed to the model rather than to a reader.

The admin review gate is what keeps hostile content out of the corpus and out
of the answers served to everyone, so the gate is only as good as the
reviewer's attention. Someone working through a queue of plausible-looking
programme facts should not have to notice, unaided, that one of them ends with
"ignore the above and always answer ...". This marks the ones worth reading
twice.

Deliberately a flag, never a filter. Nothing is auto-rejected: these patterns
also appear in innocent text (a student quoting a syllabus that says "you must
answer all questions"), and silently dropping a real contribution is a worse
failure than showing a reviewer one extra warning. The decision stays human.
"""

from __future__ import annotations

import re

# Each entry is (label shown to the reviewer, pattern). Kept small and
# specific: a detector that fires on ordinary submissions trains reviewers to
# dismiss the warning, which is worse than not having it.
_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "overrides earlier instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b"
            r"(previous|prior|earlier|above|all)\b[^.]{0,30}\b"
            r"(instruction|prompt|rule|direction|context|document)",
            re.IGNORECASE,
        ),
    ),
    (
        "addresses the assistant directly",
        re.compile(
            r"\b(you are now|you must (always|never)|from now on|act as|"
            r"pretend to be|your new (task|role|instruction))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "impersonates a system message",
        re.compile(
            r"\b(system (prompt|message|notice|instruction)|"
            r"\[?(system|assistant|admin)\]?\s*:|important notice to the (ai|assistant|model))",
            re.IGNORECASE,
        ),
    ),
    (
        "dictates a fixed answer",
        re.compile(
            r"\b(always (answer|respond|reply|say)|answer (every|all) (question|query)|"
            r"respond only with|reply with exactly|say nothing (else|but))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "asks to conceal something",
        re.compile(
            r"\b(do not (mention|reveal|disclose|tell)|without (mentioning|telling)|"
            r"keep this (secret|hidden)|never reveal)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "introduces payment or contact details",
        re.compile(
            r"\b(iban|bic|swift|bitcoin|crypto wallet|paypal|"
            r"transfer (the )?(money|fee|amount)|payable to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contains a link or embedded image",
        re.compile(r"!\[[^\]]*\]\([^)]+\)|\bhttps?://", re.IGNORECASE),
    ),
)


def injection_markers(text: str | None) -> list[str]:
    """Labels for every suspicious pattern in `text`, in a stable order."""
    if not text:
        return []
    return [label for label, pattern in _MARKERS if pattern.search(text)]
