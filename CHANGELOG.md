# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/). The topmost entry is the version
currently running - the app's version display and the /version API read this
file directly, so it is the single source of truth (no separate VERSION file
to keep in sync).

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
