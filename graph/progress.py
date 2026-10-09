"""Live progress reporting from inside graph nodes.

An answer takes 20-30 seconds, almost all of it inside retrieve and generate,
and the browser used to see nothing but a spinner until the first token.
Nodes call report_stage() at the points a person would recognise as steps;
the streaming endpoint forwards each one as an SSE 'stage' event.

The reporter travels in a ContextVar set by the node wrapper in
graph/build_graph.py, so nodes do not need a config parameter of their own
and every caller that does not listen (run_chat, Telegram, tests) pays
nothing: report_stage() is a no-op when no reporter is set.
"""
from contextvars import ContextVar
from typing import Callable

# Stage names the frontend knows how to label. Kept in one place so a typo in
# a node shows up here rather than as a silently unlabelled step in the UI.
UNDERSTANDING = "understanding"
SEARCHING = "searching"
RANKING = "ranking"
WRITING = "writing"

_reporter: ContextVar[Callable[[str], None] | None] = ContextVar("progress_reporter", default=None)


def set_reporter(reporter: Callable[[str], None] | None):
    return _reporter.set(reporter)


def reset_reporter(token) -> None:
    _reporter.reset(token)


def report_stage(stage: str) -> None:
    reporter = _reporter.get()
    if reporter is None:
        return
    try:
        reporter(stage)
    except Exception:
        # Progress is cosmetic; it must never fail an answer.
        pass
