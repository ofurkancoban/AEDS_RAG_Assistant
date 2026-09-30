# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/). The topmost entry is the version
currently running - the app's version display and the /version API read this
file directly, so it is the single source of truth (no separate VERSION file
to keep in sync).

## [1.7.4] - 2026-09-30
### Fixed
- The schedule recommendation's remaining-ECTS math trusted only the
  catalog's single fixed category per course, so a cross-listed elective
  (e.g. Computational Intelligence I/II) that a student's own ECTS Tracker
  counted toward a different, already-satisfied category still triggered
  an unnecessary extra elective recommendation. Now honors the tracker's
  own per-category bucketing when it's supplied, falling back to the
  catalog's category otherwise.

## [1.7.3] - 2026-09-30
### Fixed
- The "what should I take next semester" schedule recommendation ignored
  the ECTS Tracker widget's own record of which courses a student already
  has, always building a from-scratch full-programme plan and indexing
  into it by a stated semester number - so a student far enough along
  landed on the thesis term regardless of what they'd actually completed.
  Now skips the semester-number question entirely when that course record
  is available and computes the schedule over only what's still
  outstanding.

## [1.7.2] - 2026-09-30
### Fixed
- Three issues found by a code-review pass over today's changes:
  - `detect_contribution_node` could take an entire chat turn down with an
    unhandled exception if Laya's model call failed, discarding an answer
    `generate_node` had already produced - the old regex heuristic it
    replaced could never throw. Now fails open (skips detection) like the
    rest of this pipeline's best-effort bookkeeping.
  - `_looks_german` misclassified some ordinary English questions as
    German ("was", "die", "man" are German stopwords but also common
    English words/verbs), triggering an unnecessary, query-altering
    translation call - the opposite of 1.7.0's "English retrieval stays
    untouched" goal. Dropped the three ambiguous words from the heuristic.
  - The budget-fallback dedup fix in 1.4.0 closed the same-process race but
    not a cross-process one (two separate processes - a restart racing a
    cron script, say - could both pass the "already recorded today" check
    before either commits). `BudgetFallbackEvent.day` now has a real unique
    index as the backstop, with a one-time migration to collapse any
    duplicate rows a pre-fix database already accumulated (SQLite refuses
    to add a unique index over data that already violates it).

## [1.7.1] - 2026-09-30
### Fixed
- German corrections/new-info messages are now caught by the auto-detection
  gate. Laya (db/contribution_gate.py) routes German text to its
  multilingual checkpoint, measured substantially weaker than its English
  one on this task - missed real German corrections in testing, same as the
  regex heuristic it replaced. The message is now translated to English
  (reusing 1.7.0's translation helper) before it reaches the gate, so the
  gate always runs on the strong checkpoint; the extraction step that
  follows a positive gate still sees the original German message.

## [1.7.0] - 2026-09-30
### Added
- German-language document questions now retrieve correctly. The corpus and
  its embedding model stay English-only (still measured better for this
  corpus than a multilingual model - see README), but a German question is
  now translated to English before hybrid search/reranking, so it finds the
  same chunks an equivalent English question would; the answer itself is
  still generated in German. English retrieval is untouched - the
  translation step is skipped entirely for English questions. The tool
  router (deadlines, courses, curriculum, contacts) already handled German
  natively and is unaffected.

## [1.6.1] - 2026-09-30
### Fixed
- The source-draft preview added in 1.6.0 showed raw markdown as literal
  text - `##`/`###` markers running into the prose - in both the admin
  panel (now rendered through the same markdown renderer chat answers use)
  and the Telegram notification (which has no heading syntax at all;
  headings now get a visible `▸` marker instead of being silently deleted).

## [1.6.0] - 2026-09-30
### Added
- The admin Knowledge Base panel's Source Changes section now shows the
  LLM-drafted auto-update (for the small `AUTO_DRAFT_ELIGIBLE` allowlist in
  `scripts/source_refresh.py`) with its own Approve draft / Reject draft
  buttons, mirroring what was previously Telegram-only. Approving writes
  the draft over the curated file and re-ingests it; rejecting discards
  the draft and leaves the source flagged for the ordinary manual-dismiss
  review.

## [1.5.0] - 2026-09-29
### Added
- 16 more per-session welcome messages (now 27 total), same self-deprecating
  tone as the existing ones.

## [1.4.0] - 2026-09-29
### Added
- A favicon (previously unset, so browser tabs showed a generic icon).
### Changed
- The contribution-detection pre-filter (deciding whether a chat message is
  worth an LLM call to check for a correction/new fact) now uses a local
  calibrated classifier (Laya, see `db/contribution_gate.py`) instead of a
  regex/keyword heuristic. Measured against a real LLM oracle: higher
  precision (fewer wasted LLM calls on non-contributions) for a small
  recall cost, consistent across a hand-labelled set, real chat history,
  and the production Gemini oracle on the VPS.
### Fixed
- The budget-fallback Telegram alert ("provider's daily budget is
  exhausted...") could fire many times a day instead of once - its dedup
  lived only in one process's memory, so every restart, cron script, or
  one-off script re-sent it independently. Now deduped against the
  persistent `BudgetFallbackEvent` record instead.

## [1.3.0] - 2026-09-28
### Added
- A source that has passed its `valid_until` date is now flagged directly on
  chat responses (`expired_since` on each source and retrieved passage),
  instead of relying only on the model's own prose to mention it. The chat UI
  shows an "Outdated since ..." badge on any such passage.
- This changelog, and an in-app version indicator with a changelog popup.

## [1.2.0] - 2026-09-28
### Added
- Production errors are now reported to the admin Telegram chat automatically
  (rate-limited per endpoint and exception type), instead of only being
  visible by tailing server logs after a user reports a problem.
- The nightly database backup now also snapshots the Chroma vector store, not
  only the SQLite database.
- `scripts/deploy.sh`: a single script for building the frontend with the
  correct API URL, syncing both backend and frontend to the server, running
  the database migration, restarting the app, and waiting for it to report
  healthy again.
- Automated tests now run on every push (GitHub Actions).
### Fixed
- The Telegram error alert could silently fail to fire for the first error
  after a restart, because its cooldown timer's starting point assumed the
  server had already been running for a while.

## [1.1.0] - 2026-09-26
### Changed
- Default OpenRouter model switched to a faster, cleaner-answering release.
### Added
- OpenRouter now automatically falls back to a second, more established model
  if the primary one starts failing - protects against the primary being a
  temporary/experimental release that can be pulled or start erroring without
  notice.

## [1.0.0] - 2026-09-25
### Added
- Initial release: RAG chat assistant with admin-managed document corpus,
  hybrid retrieval and reranking, Telegram integration, and a choice of local
  (Ollama), Gemini, or OpenRouter as the answering model, switchable live from
  the admin panel without a restart.
