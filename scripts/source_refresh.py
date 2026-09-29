"""Nightly check of every source URL in data/documents/sources.json, to catch
when a source page has changed since we last looked.

Stage 1 (all sources): detect-only. The files in data/documents/ are cleaned,
not raw scrapes: a naive re-fetch of application_deadlines_table's source
page is only 4% similar to the curated file (215 curated words vs 1143 words
of page furniture) - most of these sources are a hand-picked *excerpt* of a
much larger shared page (measured: exams_faq's curated file is 821 words,
the live FAQ page it's excerpted from is 2925), so auto-overwriting from a
fresh fetch would replace curated content with either page furniture or a
mix of other programmes' unrelated content. So by default this script only
flags that the source moved and leaves a word-level diff for an admin to act
on by hand (scripts/maintenance.py handles the DB, admin uploads handle the
corpus).

Stage 2 (AUTO_DRAFT_ELIGIBLE only): for the small allowlist of sources where
the source URL's *entire* page maps onto the curated file (measured at
86-98% similarity, not an excerpt of something bigger), a significant change
also gets an LLM-drafted replacement document, sent to Telegram for a human
Approve/Reject rather than written automatically - see
_draft_curated_replacement and api/telegram_bot.py.

Why hash extracted text, not raw bytes. Measured directly: two fetches of an
unchanged source are NOT byte-identical (a 37-byte HTML diff, and the module
handbook PDF is re-encoded server-side at identical size but different bytes
each time) - hashing bytes would report "changed" on every single run.
Whitespace-normalised extracted text, run through the same loaders used for
local ingestion, IS stable across fetches and is what gets hashed here.

catalog.csv and semester_planning_rules.md have no entry in sources.json and
are never touched by this script.

Usage:
    PYTHONPATH=. python scripts/source_refresh.py
    PYTHONPATH=. python scripts/source_refresh.py --dry-run
    PYTHONPATH=. python scripts/source_refresh.py --only some_file.pdf

Suggested crontab entry (03:00 daily, ahead of maintenance.py's 03:30):
    0 3 * * * cd /path/to/AEDS_RAG && PYTHONPATH=. .venv/bin/python \
        scripts/source_refresh.py >> data/backups/source_refresh.log 2>&1
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import logging
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
USER_AGENT = "AEDS-RAG-source-check/1.0"

# Word-level diff entries beyond this length are truncated - the admin view
# needs enough to judge whether the change matters, not the entire page.
MAX_DIFF_CHARS = 6000

# Stage 2 (see module docstring): only these sources get an LLM-drafted
# replacement on a significant change. Measured 2026-09-24 - the source URL's
# entire page maps onto the curated file at similarity in the high 80s/90s%
# for these four, versus single digits to low 30s% for every other source in
# the manifest (a hand-picked excerpt of a much larger shared page, or a
# curated file written in prose that diverges structurally from the raw
# page). Re-measure before adding to this set: a low-similarity source
# drafted this way risks the LLM either padding the curated excerpt with
# irrelevant page content or guessing at what to excerpt.
#
# sports_centre was deliberately chosen for this over the other new sources
# added the same day (accommodation, international_student_checklist,
# enrolment_affairs): its content - membership prices, opening hours - is
# the kind that actually changes on its own schedule, unlike the largely
# static enrolment rules in the other three, so it is worth the effort of
# writing (and re-measuring) it close enough to the raw page to qualify.
AUTO_DRAFT_ELIGIBLE = {
    "AEDS_website_programme_overview.md",
    "AEDS_website_language_requirements.md",
    "AEDS_website_how_to_apply.md",
    "AEDS_website_sports_centre.md",
    "AEDS_website_stw_changes_2026.md",
}


# A source failing to fetch once (the site briefly down, a transient
# network blip) is normal and not worth surfacing. Three checks in a row -
# three separate days at the default crontab cadence - looks like a
# genuinely dead link (404/410, DNS failure, the page moved) rather than a
# blip, and is when this actually alerts (see decide_fetch_failure_alert).
FETCH_FAILURE_ALERT_THRESHOLD = 3


def decide_fetch_failure_alert(
    prior_count: int, succeeded: bool, threshold: int = FETCH_FAILURE_ALERT_THRESHOLD
) -> tuple[int, str | None]:
    """Pure decision: given whether this check's fetch just succeeded and
    the streak of consecutive failures going in, what count to persist next
    and whether to alert. Alerts exactly once when a streak first reaches
    `threshold` (not again on every subsequent daily failure), and once
    more with a "recovered" outcome when a source that had reached it
    succeeds again - mirroring scripts/system_health_check.py's
    decide_action, which is the same breach/recover/cooldown shape applied
    to a different kind of check."""
    if succeeded:
        if prior_count >= threshold:
            return 0, "recovered"
        return 0, None
    new_count = prior_count + 1
    if new_count == threshold:
        return new_count, "broken"
    return new_count, None


# Strips a self-regenerating "created on <date>" stamp some of the
# university's PDFs (the module handbooks) carry in their own title line -
# e.g. "... Master-Studiengang erstellt am 28.09.2026". The server re-renders
# the whole PDF with today's date baked into this line on every request, so
# without stripping it, the diff would flag "changed" daily even when the
# actual content is byte-for-byte the same underlying curriculum data -
# exactly the kind of false positive _is_significant_change's own digit rule
# cannot filter, since it exists specifically to never suppress a real
# one-token date change (a deadline). This is a known, named phrase, not a
# generic date regex, so it cannot accidentally swallow a real deadline that
# happens to sit near the word "erstellt".
_GENERATED_ON_STAMP_RE = re.compile(r"\berstellt am \d{1,2}\.\d{1,2}\.\d{4}\b")


def _normalise(text: str) -> str:
    text = _GENERATED_ON_STAMP_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _pick_suffix(content_type: str, url: str) -> str:
    """Which loader to run the fetched bytes through. Deliberately NOT the
    local filename's own suffix: a source like
    AEDS_website_language_requirements.md is a hand-curated markdown file, but
    its source URL serves live HTML - loading that HTML as plain text (the
    ".md" loader) left <script> tags and anti-scraping JS-obfuscated mailto
    markup in the extracted text, which regenerates on every request and made
    every single check report a false "changed" (found by hand, see below)."""
    content_type = content_type.lower()
    if "pdf" in content_type:
        return ".pdf"
    if "html" in content_type:
        return ".html"
    suffix = Path(url.split("?")[0]).suffix.lower()
    return suffix if suffix in {".pdf", ".html", ".htm"} else ".html"


def _extract_html_page_content(html_bytes: bytes) -> str:
    """Extract the page-specific content from a uol.de / Stud.IP CMS page,
    dropping the site chrome that surrounds it on every single page.

    Found by hand (dumping a fetched page and diffing two checks a run apart):
    outside <main>#content sits a mega-menu ('Personalities Press service News
    feeds ... Anniversary 2024: 50 years of UOL ...') and other page furniture
    that is identical on every page and changes on its own schedule (a rolling
    'x days ago' date, an anniversary banner), which made every single page on
    the site report changed on every run regardless of whether its own content
    had moved. Inside #content, its first child (id='content_header') is the
    breadcrumb trail repeating the entire site nav tree - also page-invariant.
    Scoping to #content minus content_header (falling back to <main>, then the
    whole page, for any page that doesn't follow this template) leaves just
    what's actually on that page: verified to remove all of the above noise
    across the five uol.de page templates in sources.json with zero loss of
    real content."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_bytes, "html.parser")
    scope = soup.find("div", id="content") or soup.find("main") or soup
    header = scope.find("div", id="content_header")
    if header is not None:
        header.decompose()
    for tag in scope(["script", "style"]):
        tag.decompose()
    return scope.get_text(separator=" ", strip=True)


def fetch_source_text(filename: str, url: str) -> str:
    """Fetch `url` and extract its text through the loader that matches what
    was actually served, so the hash reflects content rather than incidental
    byte/markup noise (see module docstring and _pick_suffix). HTML goes
    through _extract_html_page_content instead of the generic loader, to also
    strip the site-chrome noise described there."""
    from ingestion.loaders import load_document

    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()

    suffix = _pick_suffix(response.headers.get("Content-Type", ""), url)
    if suffix in {".html", ".htm"}:
        return _normalise(_extract_html_page_content(response.content))

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = Path(tmp.name)
    try:
        documents = load_document(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return _normalise("\n".join(document.page_content for document in documents))


# Below this, a change is judged cosmetic and kept out of the admin panel and
# Telegram entirely - just a comma, a whitespace-normalisation difference, a
# stray character. Two knobs because neither alone is right across this
# manifest's size range: a flat word count would call a real one-sentence
# change on the five-word accreditation summary "too small", and a flat
# percentage would let a genuinely large edit on the 100+ page module
# handbook hide under the floor. Whichever is more permissive wins.
SIGNIFICANCE_MIN_CHANGED_WORDS = 3
SIGNIFICANCE_RATIO_THRESHOLD = 0.01
_DIGIT_RE = re.compile(r"\d")


def _diff_tokens(old_text: str, new_text: str) -> list[tuple[str, str]]:
    """Runs difflib.ndiff once over the word-split texts and returns every
    added/removed (sign, word) pair, in order. Both word_diff and
    _is_significant_change are built on this single pass, so what an admin
    sees in the diff and what decided whether they see it at all can never
    disagree about which words actually changed."""
    old_words = old_text.split()
    new_words = new_text.split()
    tokens = []
    for op in difflib.ndiff(old_words, new_words):
        tag, word = op[0], op[2:]
        if tag in ("+", "-"):
            tokens.append((tag, word))
    return tokens


def word_diff(tokens: list[tuple[str, str]]) -> str:
    """A compact word-level diff: '[-removed]' / '[+added]' tokens in their
    original order, dropping unchanged spans entirely. Not meant to be a full
    context view - just enough for an admin to judge whether the source
    change is worth re-curating, with the source URL there for the rest."""
    diff = " ".join(f"[{tag}{word}]" for tag, word in tokens)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + " …(truncated)"
    return diff


def _is_significant_change(tokens: list[tuple[str, str]], old_word_count: int) -> bool:
    """Whether a hash flip is worth surfacing, not just recording.

    A pure size threshold is the wrong axis on its own: the highest-stakes
    edit this corpus can have is a one-token date change on the deadlines
    page ('15 Oct' -> '16 Oct') - tiny by word count, never safe to suppress.
    So any changed token containing a digit is always significant regardless
    of size; everything else has to clear the small floor above, which exists
    only to swallow cosmetic edits, not to hide real content."""
    changed_words = [word for _, word in tokens]
    if any(_DIGIT_RE.search(word) for word in changed_words):
        return True
    floor = max(SIGNIFICANCE_MIN_CHANGED_WORDS, int(old_word_count * SIGNIFICANCE_RATIO_THRESHOLD))
    return len(changed_words) >= floor


def _draft_curated_replacement(old_markdown: str, live_text: str) -> str | None:
    """Asks the configured chat LLM (graph.nodes.get_llm - same provider
    selection as the assistant itself, temperature=0) to update a curated
    document to match a changed source page. Only called for
    AUTO_DRAFT_ELIGIBLE filenames, where the source URL's entire page IS the
    curated file - this is a targeted reformat of known-current content, not
    a general-purpose auto-curator that decides what to keep.

    Best effort: any failure is logged and returns None, which leaves the
    change in the same manual-dismiss-only state every other source gets -
    a broken draft call should never be the reason a real change goes
    unflagged."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from graph.nodes import get_llm

    system = (
        "You maintain a curated knowledge-base document for a university "
        "programme's RAG assistant. You are given the CURRENT document and "
        "the CURRENT text of the web page it was built from, which has since "
        "changed. Rewrite the document so it reflects what the page says now, "
        "keeping its structure, heading, and plain-text style as close to the "
        "original as the new content allows.\n\n"
        "Rules: change only what the page's content actually changed. Never "
        "invent, infer, or carry over any fact, number, or date that is not "
        "present in the page text you were given. If something in the old "
        "document no longer appears on the page, remove it. Output only the "
        "replacement document text - no preamble, no explanation, no code "
        "fence."
    )
    human = f"CURRENT DOCUMENT:\n{old_markdown}\n\nCURRENT PAGE TEXT:\n{live_text}"

    try:
        response = get_llm().invoke([SystemMessage(content=system), HumanMessage(content=human)])
        draft = (response.content or "").strip()
        return draft or None
    except Exception as exc:
        logger.warning("Draft generation failed: %s", exc)
        return None


# How far ahead of a valid_until date (see sources.json, e.g. the deadlines
# table and stw_changes_2026) to start warning. Kept simple and repeated
# rather than one-shot: a nightly reminder for up to two weeks is cheap and
# never silently missed, versus tracking whether a particular expiry was
# already acknowledged, which nothing else in this file's state does.
EXPIRY_WARNING_DAYS = 14


def check_expiring_documents() -> None:
    """Best-effort Telegram reminder for documents whose valid_until (see
    sources.json) is already past or within EXPIRY_WARNING_DAYS - the kind of
    file that goes stale on its own schedule regardless of whether its
    source URL's content ever changes (e.g. an annual deadlines table, or an
    announcement page for a specific year), so source_refresh's normal
    hash-diff check will not by itself prompt anyone to go re-scrape it."""
    from db.models import IngestedDocument, SessionLocal

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=EXPIRY_WARNING_DAYS)

    session = SessionLocal()
    try:
        rows = session.query(IngestedDocument).filter(IngestedDocument.valid_until.isnot(None)).all()
        # Compared in Python, not the SQL WHERE clause: SQLite has no native
        # timezone-aware datetime type, so a value written tz-aware (see
        # ingestion/chunker.py's manifest parsing) can round-trip back naive
        # - the same mismatch api/routes_admin.py's _is_expired already
        # guards against, normalised here the same way.
        expiring = []
        for doc in rows:
            valid_until = doc.valid_until
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if valid_until <= horizon:
                expiring.append((doc.filename, valid_until))
        expiring.sort(key=lambda pair: pair[1])
    finally:
        session.close()

    if not expiring:
        return

    from api.telegram_bot import notify_expiring_documents

    notify_expiring_documents(expiring)


def refresh_sources(
    only: str | None, dry_run: bool
) -> tuple[list[tuple[int, str, str, str | None]], list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Checks every manifest entry that has already been locally ingested.
    Returns (changed, broken, recovered):

      changed   - (id, filename, url, draft) for every source found changed.
                  id is what a Telegram button's callback_data carries (see
                  api/telegram_bot.py), since several filenames in this
                  manifest are well over Telegram's 64-byte callback_data
                  limit. draft is the LLM-proposed replacement text for an
                  AUTO_DRAFT_ELIGIBLE file (None otherwise, or if drafting
                  failed - see _draft_curated_replacement).
      broken    - (filename, url, error) for every source whose fetch has
                  now failed FETCH_FAILURE_ALERT_THRESHOLD checks in a row -
                  see decide_fetch_failure_alert.
      recovered - (filename, url) for every source that had reached that
                  threshold and has now fetched successfully again.
    """
    from db.models import IngestedDocument, SessionLocal, init_db
    from ingestion.chunker import load_source_urls

    # Standalone cron invocations never run api/main.py's startup, which is
    # what normally applies a newly added column (source_draft) to an
    # existing database file - without this, a fresh deploy's first cron run
    # would hit "no such column" the moment it tried to write one.
    init_db()

    manifest = load_source_urls()
    if only:
        manifest = {name: url for name, url in manifest.items() if name == only}
        if not manifest:
            logger.error("%s: no source URL in sources.json", only)
            return []

    changed: list[tuple[int, str, str, str | None]] = []
    broken: list[tuple[str, str, str]] = []
    recovered: list[tuple[str, str]] = []
    session = SessionLocal()
    try:
        for filename, url in sorted(manifest.items()):
            existing = (
                session.query(IngestedDocument).filter(IngestedDocument.filename == filename).first()
            )
            if existing is None:
                logger.info("%s: not yet ingested locally, skipping", filename)
                continue

            now = datetime.now(timezone.utc)
            try:
                live_text = fetch_source_text(filename, url)
            except Exception as exc:
                new_count, outcome = decide_fetch_failure_alert(existing.fetch_failure_count, succeeded=False)
                logger.warning(
                    "%s: fetch failed (%s) - %d consecutive failure(s)", filename, exc, new_count
                )
                if not dry_run:
                    existing.fetch_failure_count = new_count
                    existing.last_fetch_failure_at = now
                    session.commit()
                if outcome == "broken":
                    broken.append((filename, url, str(exc)))
                continue

            new_count, outcome = decide_fetch_failure_alert(existing.fetch_failure_count, succeeded=True)
            if outcome == "recovered":
                recovered.append((filename, url))
            existing.fetch_failure_count = new_count

            new_hash = hashlib.sha256(live_text.encode("utf-8")).hexdigest()

            if existing.source_text_hash is None:
                logger.info("%s: first check, baseline recorded", filename)
                if not dry_run:
                    existing.source_text_hash = new_hash
                    existing.source_text_snapshot = live_text
                    existing.last_checked_at = now
                    session.commit()
                continue

            if new_hash == existing.source_text_hash:
                logger.info("%s: unchanged", filename)
                if not dry_run:
                    existing.last_checked_at = now
                    session.commit()
                continue

            old_snapshot = existing.source_text_snapshot or ""
            tokens = _diff_tokens(old_snapshot, live_text)
            significant = _is_significant_change(tokens, len(old_snapshot.split()))

            if not significant:
                logger.info(
                    "%s: changed but not significant (%d word(s) touched), baseline updated silently",
                    filename, len(tokens),
                )
                if not dry_run:
                    existing.source_text_hash = new_hash
                    existing.source_text_snapshot = live_text
                    existing.last_checked_at = now
                    session.commit()
                continue

            diff = word_diff(tokens)
            logger.info("%s: SOURCE CHANGED since last check (%d diff chars)", filename, len(diff))

            draft = None
            if filename in AUTO_DRAFT_ELIGIBLE and not dry_run:
                from config import settings

                curated_path = settings.documents_dir / filename
                old_markdown = curated_path.read_text(encoding="utf-8") if curated_path.exists() else ""
                draft = _draft_curated_replacement(old_markdown, live_text)
                logger.info("%s: draft %s", filename, "generated" if draft else "failed/skipped")

            if not dry_run:
                existing.source_text_hash = new_hash
                existing.source_text_snapshot = live_text
                existing.source_diff = diff
                existing.source_draft = draft
                existing.last_checked_at = now
                existing.last_changed_at = now
                session.commit()
            changed.append((existing.id, filename, url, draft))
    finally:
        session.close()

    return changed, broken, recovered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen, change nothing")
    parser.add_argument("--only", help="Check a single filename instead of every manifest entry")
    args = parser.parse_args()

    print(f"source refresh run {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    changed, broken, recovered = refresh_sources(only=args.only, dry_run=args.dry_run)
    print(f"{len(changed)} source(s) changed since their last check")
    print(f"{len(broken)} source(s) newly flagged as broken, {len(recovered)} recovered")
    if changed and not args.dry_run:
        # Each notification carries its own button(s); a running API server's
        # background poller (api/telegram_bot.start_background_polling) is
        # what handles the press - this cron job only ever sends.
        from api.telegram_bot import notify_source_change, notify_source_draft

        for doc_id, filename, url, draft in changed:
            notify_source_change(doc_id, filename, url)
            if draft:
                notify_source_draft(doc_id, filename, draft)

    if (broken or recovered) and not args.dry_run:
        from api.telegram_bot import _notify_admins

        for filename, url, error in broken:
            _notify_admins(
                f"Source link may be broken: {filename} ({url})\n"
                f"Failed {FETCH_FAILURE_ALERT_THRESHOLD} checks in a row: {error}"
            )
        for filename, url in recovered:
            _notify_admins(f"Source link recovered: {filename} ({url})")

    if not args.dry_run:
        check_expiring_documents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
