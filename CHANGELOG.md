# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/). The topmost entry is the version
currently running - the app's version display and the /version API read this
file directly, so it is the single source of truth (no separate VERSION file
to keep in sync).

## [1.10.0] - 2026-10-10
### Added
- Recent conversations. Each visitor's earlier conversations are listed in
  the side navigation, titled by their first question; opening one restores
  every turn with its citations, evidence and ratings, and a follow-up
  continues the same thread. query_log now keeps each answer's sources and
  passages in order (evidence_json), which is what lets "[2]" point at the
  right passage again. Only the caller's own threads can be listed or opened.
- German interface. An EN/DE switch in the header translates the student
  screens (start screen, topics, composer, progress, sources, dialogs); the
  choice is remembered per browser and English stays the default. Every
  German topic and start question was run through the pipeline and answers
  in German from the right documents. Staff screens stay English.
- New university documents: the semester contribution (amounts by student
  group for the winter semester 2026/27, bank details, the 2024/25 refund),
  the Germany semester ticket (how to retrieve it, where it is valid, what
  it does not cover) and the library opening hours, with topics for each.
- A thumbs-down now reaches the programme team: admins get a Telegram alert
  with the question and answer, and the answer moves to the top of the
  review queue under a new "Rated unhelpful" filter until it is reviewed
  again. It never changes an answer's review status by itself. Students
  see a short note that the answer will be checked.
### Changed
- Faster answers: document search and reranking start at the same time as
  the tool router instead of after it, and are skipped when a tool answers.
  Sources are sent with the answer instead of waiting for contribution
  detection, which now follows as its own event.
- OpenRouter calls ask for providers that neither store nor train on
  prompts (provider.data_collection = "deny", checked working with both
  models; OPENROUTER_DENY_DATA_COLLECTION switches it off). The privacy
  note under the input says so.
- pm2 restarts the app if it ever passes 4.5 GB (it holds about 2.9 GB of
  embedding and reranker models), set by scripts/deploy.sh.
- Answer review shows the model's citation numbers as chips.
### Fixed
- German questions: "Studierendenwerk" and similar names are kept in German
  when a question is translated for search (it became "student union
  dormitory" and the housing documents were missed); deadline and
  examinations office answers are translated for a German question instead
  of arriving in English; more German questions are recognised as German.
- An admission question in German was sent to the examinations office
  lookup and answered with the Examining Board chair.
- "Which professors teach on this programme?" answered that the documents
  name no professors: it was routed to the curriculum listing, which has no
  lecturer names, instead of the course catalogue.
- A library question naming a campus (Wechloy) was sent to the course
  catalogue, whose campus field replaced the document search.
- Exam procedure questions (a lost TAN list, what the examinations office
  does) were answered with only the Examining Board chair's name: the
  contact lookup is now used only when a question asks who that person is.

## [1.9.0] - 2026-10-07
### Added
- Live answer progress. An answer takes 20-30 seconds and the page used to
  show three dots for all of it; the streaming endpoint now sends a 'stage'
  event as the pipeline reaches each step (understanding the question,
  searching the documents, selecting passages, writing), shown as a step
  list with a progress bar and a running timer. Every step marked done is
  one the backend actually reported (graph/progress.py); a structured
  lookup that skips document search shows those steps as skipped.
- Inline citations. Retrieved passages are numbered in the model's context
  and it tags each fact with the passage it came from; the chat renders
  "[2]" as a citation that previews the passage on hover. Numbers with no
  matching passage are stripped server-side, and Telegram replies strip
  them all (they cannot be opened there).
- An Evidence panel beside the conversation on wide screens: the selected
  answer's passages with quoted text, relevance, how often each is cited,
  outdated warnings, and which were retrieved but not cited. Clicking a
  citation highlights its passage there; on narrower screens the sources
  sit under the answer and a citation opens the passage as a sheet.
- University and City & living questions alongside the programme ones
  (re-registration, leave of absence, arriving as an international
  student, university sports, Studierendenwerk housing, rent, canteen
  prices), each verified to answer from the documents. Every answer is
  labelled with the domain its main source belongs to.
### Changed
- The student interface is redesigned as an institutional service rather
  than a chat app: a "Student Assistant" header with the programme it
  serves, topic navigation grouped by domain (a drawer on phones), a start
  screen with one card per domain, and each question and answer as one
  card. One sans-serif family (IBM Plex, self-hosted - Google Fonts would
  send every visitor's IP to Google), university blue, neutral greys.
- Everything programme-specific (name, domains, topics, start questions,
  which document belongs to which domain, how each document is named) now
  lives in frontend/src/config/programme.ts. Serving another programme or
  the whole university means adding configuration, not redesigning.
- Version and visitor count moved from the viewport corners into the
  navigation footer; every dialog is a bottom sheet on phones and closes
  with Escape. Admin views share the new design tokens.
### Fixed
- The production OpenRouter model, stealth/space-bunny-alpha, had been
  withdrawn ("No endpoints found"): every answer first failed against it and
  then fell back silently. The default is now apodex/apodex-1.1-mini
  (13/15 on a hard golden-eval subset at a 4.2s median, the fastest model
  that passed), with dots-studio/dots-3-note-preview (15/15, 45-46/47 on the
  full set, slower) as the fallback - chosen by measuring OpenRouter's free
  models on this project's own tasks.
- "Writing the answer" took 8-25s before the first word with reasoning
  models: they spent up to 2,500 hidden reasoning tokens first. OpenRouter's
  reasoning is now set per call kind - off for answer generation, low effort
  for the router, translation and classifier, where it made tool choice
  consistent (15/15 instead of missing the catalog tool on 2 of 5 runs) at
  no extra latency.
- Plain new-information messages ("The lab is in room A14") were never
  flagged for review: the Laya gate scores them near zero. A plain-statement
  rule now passes them too (25/25 vs 15/25 on hand-written contributions,
  0/76 false passes on real questions; on real production traffic, 10 of 70
  messages reach the classifier instead of 6).
- "Which courses are taught only in German?" listed the 30-ECTS thesis
  module, which Stud.IP records as German though it is not a taught course.
- A catalog search the router made by mistake and that matched nothing was
  still handed to the model as the only context, so it answered "no
  information" to questions the documents do answer; it now falls through
  to document search.
- Router examples for "Who is <name>?" and first-semester course questions,
  which some models otherwise sent to document search.
- The model choice no longer lives in .env. A model line there outranked
  the code default and is what kept the withdrawn model in production;
  models now come from config.py, switchable live in the admin panel, and
  scripts/deploy.sh removes OPENROUTER_MODEL / OPENROUTER_FALLBACK_MODEL
  from the server's .env (after a dated backup).
### Added
- scripts/check_llm_models.py: verifies the configured OpenRouter models
  still exist and flags a model line left in .env. Runs on every deploy
  (clearing an admin-panel value that names a withdrawn model, so the code
  default applies after the restart) and in the nightly maintenance run
  (alert-only, to the admin Telegram chat) - a withdrawn model can no longer
  hide behind the fallback for days.

## [1.8.4] - 2026-10-05
### Fixed
- Tapping the message box on iOS Safari zoomed the whole page in instead
  of just opening the keyboard - Safari auto-zooms to focus any input
  whose computed font-size is under 16px, and the box was 12px there. Now
  16px on mobile (14px unchanged on `sm`+, where this doesn't trigger);
  the placeholder keeps its smaller size on its own via `placeholder:`,
  which Safari's zoom check does not look at. With the zoom gone, focusing
  the box now does what it always should have: the keyboard opens and the
  browser's native scroll-into-view brings the box up above it, instead of
  the page jumping to a zoomed-in state first.

## [1.8.3] - 2026-10-05
### Fixed
- The site loaded slowly on mobile. nginx was serving the frontend build
  completely uncompressed and with no cache headers - the ~430KB JS bundle
  and ~68KB CSS bundle went out at full size on every single visit, which
  a desktop's fast, low-latency connection mostly hid but a cellular
  connection did not. Added gzip for text/JS/CSS/SVG and a year-long
  immutable cache for the hashed `/assets/` files (safe: Vite renames them
  on every build), while `index.html` itself stays always-revalidated so
  it keeps pointing at the right build. Measured on a simulated slow-4G
  connection: full page load dropped to roughly a third of its prior time.

## [1.8.2] - 2026-10-05
### Fixed
- On mobile, the message input's placeholder text wrapped to a second line
  that rendered clipped behind the Submit button - the textarea reserved
  128px on the right for a "Submit" label + icon regardless of screen
  width, leaving too little room for the placeholder to fit on one line.
  The button is icon-only below `sm` (its "Submit" label still shows on
  larger screens), so the textarea needs far less clearance there.

## [1.8.1] - 2026-10-05
### Changed
- On mobile, the sidebar (Quick Academic Queries, Knowledge Base panel,
  New conversation) is now a slide-over drawer, opened from a "Quick
  queries" bar above the conversation, instead of a column stacked above
  the chat. 1.8.0 already freed up the conversation's height; this gives
  it the entire screen by default rather than sharing it with a second,
  always-open panel. Unchanged on desktop, where the sidebar remains a
  permanent column.

## [1.8.0] - 2026-10-05
### Fixed
- The chat view was effectively unusable on a phone. Its footer (the
  "Suggested Queries" chips, the input box, and the disclaimer text) had a
  large fixed height that, inside a mobile-sized chat card, left only
  ~43px for the actual conversation - the welcome message and every answer
  rendered into a sliver too short to show anything. The suggested-query
  chips (which duplicate the sidebar's own Quick Academic Queries buttons)
  are now hidden below the `sm` breakpoint, giving the conversation area
  its height back.
- The app shell used `h-screen` (100vh) for a layout meant to fill exactly
  one viewport and never scroll. On mobile Safari, 100vh is measured
  against the browser chrome's hidden state, so content could render
  partly behind the address bar instead of shrinking to fit above it.
  Switched to `h-dvh`, which tracks the real visible viewport.
- The version and visitor-count badges are fixed to the viewport's bottom
  corners; on mobile, where the chat column fills the viewport exactly,
  they sat on top of the disclaimer's last line instead of beside the
  card. Added bottom clearance on mobile only.

## [1.7.5] - 2026-09-30
### Fixed
- The schedule recommendation dropped a course entirely once a student
  marked it merely "planned" in the ECTS Tracker, even though a planned
  course hasn't actually been taken yet and (especially if compulsory)
  should keep surfacing as a real next-semester suggestion. Only completed
  and in-progress courses are excluded now.
### Changed
- Among the remaining candidate courses for a term, compulsory ones now
  sort ahead of electives, so a term with more outstanding work than fits
  in one semester fills with mandatory modules first.
- The ECTS Tracker widget's course-context line format changed from "Codes
  already completed, in progress, or planned:" to "Codes already completed
  or in progress:" (planned courses are parsed separately now, see above) -
  requires the ECTS Tracker project to be deployed with the matching format.

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
