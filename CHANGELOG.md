# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/). The topmost entry is the version
currently running - the app's version display and the /version API read this
file directly, so it is the single source of truth (no separate VERSION file
to keep in sync).

## [1.10.29] - 2026-10-12
### Added
- "What's my GPA?" is now answered from the ECTS Tracker widget's own
  overall and per-category GPA lines (new in the widget's injected
  context) - found live: with the GPA numbers sitting right there in the
  context, the LLM still refused to answer, treating a student's own
  tracker data as outside the "official programme documents" its system
  prompt restricts it to. No course-context toggle, or no graded completed
  courses yet, falls back to the regular answer as before.

## [1.10.28] - 2026-10-12
### Added
- The per-category ECTS breakdown now also shows In Progress and Planned
  ECTS, not just Completed - "Still Needed" subtracts all three from each
  category's target, matching AEDS_ECTS_Tracker's own "remaining" figure in
  its UI exactly. In-progress/planned courses aren't given a ready-made
  ECTS subtotal in the widget's context (only completed is), so their
  codes are looked up against the catalog.

## [1.10.27] - 2026-10-12
### Added
- "How many ECTS do I need to graduate?" now shows a per-category remaining
  breakdown (completed/required/remaining per component) when the ECTS
  Tracker widget's course-progress context is present, instead of just the
  fixed totals - computed deterministically from the widget's own
  per-category summary lines rather than left to the LLM, which has
  gotten this kind of category-by-category subtraction wrong before (see
  the earlier schedule-recommendation fixes). A category with zero
  progress (most commonly Thesis, before a student starts it) is still
  included as a 0/required row, since the widget only writes a line for a
  category with at least one logged course - omitting it would otherwise
  silently total less than the real 120 ECTS. Without the course-context
  toggle on, this question is answered exactly as before.

## [1.10.26] - 2026-10-12
### Fixed
- The schedule recommender now prefers a student's already-planned
  electives (ECTS Tracker status "planned") over a catalog course they've
  never touched - found live: a student who had already planned "Spatial
  Econometrics" for Empirical and "Computational Intelligence I" for
  Specialization was instead recommended "Operations Management", a course
  they'd never shown any interest in, because planned and never-touched
  electives were weighted identically in the selection pool. Also fixes a
  cross-listing gap this surfaced: a planned course catalogued under a
  different category than the student counts it toward (the same situation
  the completed-codes category override already handled) was silently
  dropped from the recommendation entirely rather than offered back for the
  category the student actually planned it under.

## [1.10.25] - 2026-10-12
### Added
- Schedule recommendations are more explanatory: a short lead-in explains
  what the list is (compulsory requirements due, plus electives toward each
  component's remaining ECTS target), and each elective pick now shows up
  to 2 other courses from the same component that would have counted
  toward the same requirement, not just the one the algorithm landed on -
  e.g. "Also counts: Computational Intelligence I (inf535), Business
  Intelligence II (inf607)" under a picked elective. Applies to both the
  single-term and full multi-semester plan answers.

## [1.10.24] - 2026-10-12
### Fixed
- The schedule-request hint phrases (e.g. "make a schedule") now tolerate
  one inserted word ("make a FULL schedule") and still match - previously
  an exact-substring check, so a phrasing like "Can you make a full
  schedule until graduation?" missed every hint entirely and fell through
  to a free-form LLM answer instead of the deterministic schedule builder.
  Deliberately bounded to one inserted word, not a general fuzzy match -
  tightened from two after it let an unrelated sentence ("make an
  appointment, a form, and then maybe a schedule for my doctor visit")
  false-match "make a schedule".

## [1.10.23] - 2026-10-12
### Added
- The schedule recommender now factors in AEDS_ECTS_Tracker's anonymous
  course-difficulty ratings (scripts/update_ratings.py, nightly, straight
  after update_catalog.py): when a category's remaining ECTS target can be
  met by more electives than are needed, the ones students rated easier are
  preferred over harder ones with the same offering season. A course's
  difficulty (e.g. "difficulty 1.7/5 (3 votes)") is now also shown next to
  it in the answer, rated or not, so the student sees the same information
  the pick was based on. Unrated courses are treated as a neutral mid-scale
  3.0 - neither favored nor buried - and keep varying between requests as
  before.

## [1.10.22] - 2026-10-12
### Fixed
- The "next semester" recommendation now checks each candidate course's real
  offering history (catalog.csv's semesters_offered/extra_semesters) instead
  of only its generic WiSe-or-SoSe season: a course with a confirmed gap
  year (e.g. offered every SoSe except one) is skipped in favor of an
  available elective, or, if compulsory, kept but flagged with a note to
  double-check with the examinations office - the "suggest an alternative
  when needed" rule the recommendation didn't previously follow.
- When the question doesn't state a season, the default also now follows
  the real calendar (the actual upcoming WiSe or SoSe) instead of always
  assuming WiSe - asking in autumn/winter previously still labelled the
  answer "(WiSe)" even though the real next term is a SoSe.
### Added
- "Which courses should I take this semester?" is now answered for the
  semester actually in progress, not the upcoming one - previously it was
  silently treated the same as "next semester", which during WiSe could
  recommend SoSe-only courses for a term that's already running. It also
  skips the "which semester are you starting?" clarifying question, same as
  a full-plan request - neither needs it anymore.

## [1.10.21] - 2026-10-12
### Changed
- Router decisions are stored in a route_decisions table as well as in
  memory, so a restart or deploy no longer empties the 24-hour cache. The
  key includes a fingerprint of the router prompt, tool definitions and
  router model: a deploy that changes any of them asks the router again
  instead of reusing a decision made under the old ones. A database error
  only means a cache miss.
- Measured but not changed: trimming the context sent to the answer model.
  Parent sections make up 68% of it (median 6,000 characters), but every
  smaller variant lost golden facts (children only 64/67, a 4,000-character
  window 66/67), and on the ten largest contexts the most aggressive cut
  saved 0.4s at the median, partly by producing shorter answers.

## [1.10.20] - 2026-10-12
### Removed
- Reverted 1.10.19: the R2 off-site backup upload and the nginx
  Cloudflare real-IP setting (removed from the VPS as well). Backups stay
  local in data/backups/; the Cloudflare reranker (1.10.18) is unchanged.

## [1.10.19] - 2026-10-12
### Added
- Off-site backups: each night's encrypted app.db and Chroma snapshots are
  uploaded to a Cloudflare R2 bucket (newest 30 of each kept), with a
  Telegram alert if the upload fails. Unencrypted snapshots are never
  uploaded. Off until R2_BUCKET and its keys are set.
- nginx takes the visitor's address from CF-Connecting-IP on connections
  from Cloudflare's ranges, so rate limits keep working per visitor once
  the domain is proxied through Cloudflare (docs/deployment.md).
### Not changed
- Embeddings stay local. Workers AI's bge-large-en-v1.5 is not
  vector-identical to the local one (cosine 0.97; vector-search top-10
  matched on 12 of 30 questions), so it would mean re-embedding the corpus,
  for no speed gain (253ms vs 268ms) and with search depending on one
  provider with no fallback.

## [1.10.18] - 2026-10-12
### Changed
- Reranking runs on Cloudflare Workers AI's hosted bge-reranker-base (the
  same model) instead of the VPS CPU: median 544ms instead of 3066ms over
  30 golden questions on the VPS. Golden-set retrieval stays at 73/73
  context recall and 59/59 source hits; the same questions fall under the
  relevance gate. The hosted model reads more of each passage, so some
  scores differ ("Can I get more time for my Master's thesis?" 0.13
  instead of 0.03). Any error or a 3s timeout falls back to the local
  model, which stays loaded, and the API is then skipped for 5 minutes.
  Off when CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are unset.

## [1.10.17] - 2026-10-12
### Changed
- A question that names nothing a routing tool knows about (no
  application, course, lecturer, curriculum or examinations office cue, no
  catalog course name, abbreviation or lecturer surname) skips the routing
  call and goes straight to the document search. Over the 111 golden
  questions it skips 64; of the 29 the router sends to a tool it lets 28
  through, and the remaining one (thesis credit points) is answered from
  the regulations just as well. The search already ran alongside the
  router, so the saving is the router's overrun: about 0.7s at the median,
  around 6s for the slowest tenth, and one LLM request per skipped
  question.
- Measured but not changed: the reranker takes about 3s of the 3.3s
  retrieval on the VPS CPU. ONNX Runtime was no faster, int8 quantization
  changed the top four passages in 8 to 17 of 30 questions, and fewer
  candidates or shorter passages each lost a golden case.

## [1.10.16] - 2026-10-12
### Added
- /review in the Telegram admin bot: pending answers one at a time, most
  asked first, with their sources; Approve, Reject or Skip sends the next
  one straight away.
- Thumbs-down ratings become draft test cases on Sundays, next to the ones
  from review decisions, with the downvoted answer's figures as candidates
  to rule out.
- Nightly retrieval check (golden set through the real search, no LLM
  calls): a Telegram alert when recall or source hits drop, for example
  after the source refresh re-ingested a changed document.
- Time to the first word on screen and the router step's time (or a router
  cache hit) are logged per answer; the weekly summary gives p50/p95 answer
  time, first-word time and the router cache rate.
### Changed
- A model OpenRouter reports as unavailable is skipped for 6 hours, going
  straight to the fallback model, with one Telegram alert. Until now every
  question paid for a failed call first and the daily check noticed a day
  later (Kilo withdrew apodex on 2026-10-12).
- The retrieval eval checks tool-answered questions (deadlines,
  examinations office, course catalog) against the tool's output instead of
  the search, which never sees that data: 73/73 context recall and 59/59
  source hits. The deploy gate rises from 88%/95% to 96%/96%.
### Fixed
- Test cases mined on the server were deleted by the next deploy (rsync
  --delete over tests/). Drafts now live in data/eval/case_drafts.json,
  which deploys leave alone.

## [1.10.15] - 2026-10-12
### Added
- Documents on the broadcast fee (Rundfunkbeitrag: amount, shared flats,
  student residences, exemption rules for international students) and on
  the Language Centre's German courses (free for enrolled students, levels,
  credits, placement test, registration dates), both checked against the
  official pages, with six golden cases.
- Weekly summary to Telegram on Mondays: questions and conversations,
  unanswered questions, ratings, review queue, latest golden-set score and
  the document contradiction check (scripts/weekly_report.py).
- Golden set: 16 German questions and 8 multi-turn conversations.
### Changed
- A follow-up question now searches with itself first plus the earlier
  user questions, without the previous answer. The answer's own wording
  pulled in unrelated passages ("Where do I apply for it?" after a
  residence-permit answer that mentioned the Bürgerbüro).
- Router decisions are cached for 24 hours per normalised question, so a
  repeated question skips the routing call.
### Fixed
- The embedding model and the reranker now run one pass at a time.
  Speculative retrieval searched on several threads at once, and on Apple
  Silicon (MPS) three concurrent passes spun forever without progress,
  hanging the multi-turn eval for 28 minutes. Each pass takes milliseconds,
  so the lock costs next to nothing.

## [1.10.14] - 2026-10-12
### Changed
- The number guard now regenerates. Measured in log mode over the full
  golden set on both models (160 answers): 4 triggers, none on a correct
  figure - a credit total and a count of lecturers the model computed
  itself, a difference it showed its working for (now accepted) and a
  grade value from general knowledge.
- The relevance gate is 0.01 instead of 0.05. Reranker scores do not
  separate in-scope from off-topic questions ("How do I renew a US
  passport?" 0.75, "Can I get more time for my Master's thesis?" 0.03), so
  colloquial questions were refused although the right passage ranked
  first. Of 12 colloquial in-scope questions 11 are now answered; the
  off-topic ones that reach the model are refused by it.
- The answer model stays apodex: on the 80-case golden set apodex and dots
  each scored 79/80 (the same case, now fixed by the gate change); apodex
  is faster and kept German answers and their figures intact. dots keeps
  routing.

## [1.10.13] - 2026-10-11
### Added
- Number guard: every figure in an answer (10 or more) is checked against
  the context, question and conversation the model was given; separators
  are ignored ("11.904" = "11,904") and a figure the answer derives from
  two supported ones (120 - 30 = 90) counts as supported. When a figure is
  unsupported it is logged, and in "regenerate" mode the answer is written
  once more with that figure named, without streaming the second attempt.
  Found because a model turned "280 half days" into "200" while answering
  in German. Ships in "log" mode until its false-alarm rate is measured.
- Weekly contradiction check (scripts/check_contradictions.py, Sundays
  from maintenance): reports documents that state different values for
  the same fact, with a Telegram summary. It finds both of this month's
  real conflicts (thesis admission 2 vs 60 ECTS, thesis grading 6 vs 8
  weeks) when the old documents are put back, and nothing today.
- Weekly golden-set runs are recorded (eval_runs) and shown in the admin
  analytics as a trend with the failed cases; the Telegram message now
  gives the score and the failed case ids.
- deploy.sh runs the retrieval check (golden set, no LLM calls) first and
  stops below 88% context recall or 95% source hits.
- The answer review queue shows how often each question was asked and
  lists the most-asked first. scripts/refresh_review_queue.py regenerates
  pending answers whose sources were replaced and rejects, with a note,
  entries that must never be served to someone else.
### Changed
- A student's own ECTS Tracker progress and small talk no longer enter or
  come out of the reviewed-answer cache: two progress messages read alike,
  so an approved plan could have been served for someone else's record.
- The reply when nothing relevant is found names who can help (the
  Examinations Office via AskOne, the International Office, the
  Studierendenwerk, the AStA) and is given in German for German questions.
- Long dashes in answers become plain hyphens; ranges like 15-25 keep
  theirs. The header shows "Assistent" on phones instead of the cut-off
  "Studierenden-Assistent".
- The university-wide language page now starts with this programme's
  requirement (English B2, no German) before the German-taught programmes'
  rules.

## [1.10.12] - 2026-10-11
### Added
- Three documents for international students, each checked against the
  official page: the residence permit in Oldenburg (the Hochschulservice
  at Pferdemarkt 14, when to apply, the documents, proof of funding of
  EUR 11,904 a year, the fee), health insurance (statutory versus private,
  no later switch to statutory, students under and over 30, EHIC and
  agreement countries) and working while studying (140 full or 280 half
  days a year for non-EU students, no limit as a student assistant, the
  minimum wage). The production log was too small to show real content
  gaps, so these were chosen as the questions international Master's
  students most need answered. Seven golden cases: 0/7 -> 7/7 with apodex
  (all refused before) and 7/7 with dots; context recall and source hits
  on the existing cases unchanged.

## [1.10.11] - 2026-10-11
### Fixed
- Production restarted in a loop for about 25 minutes. pm2's memory
  ceiling (4.5 GB, set in 1.10.0) was below what the app needs once a
  message that is not a question loads the contribution classifier: the
  retrieval models take 2.9 GB and the classifier, preloading every Laya
  checkpoint, another 4.6 GB on the VPS. It now loads only the checkpoint
  it uses (2.5 GB), greetings and thanks skip contribution detection
  altogether, and the ceiling is 7.5 GB (about 5.4 GB steady, 6.2 GB peak
  measured). The ceiling was raised by hand on the VPS to end the loop
  before this release.

## [1.10.10] - 2026-10-11
### Fixed
- Greetings, thanks and "what can I ask you?" got the "the programme's
  documents do not contain information on that" refusal; in production
  that was the reply to "hi", "How are you?" and "what else can I ask".
  They now get a short welcome in the user's language (English or German)
  naming what the assistant covers, with no LLM call. Real questions that
  start with a greeting ("Hi, when is the deadline?") are unaffected.
- "Am I on track to graduate?" was refused: the reranker scored that
  personal wording below the relevance gate (0.02) although "What do I
  need to graduate?" scored 0.99. Such questions now search for the
  graduation requirements, and the answer gives them (120 ECTS, the
  components, the thesis) while saying it cannot see the student's own
  progress. Golden cases from these production messages: 0/5 -> 5/5 on
  both models.
- (Reverted the same day) Loading the contribution classifier during the
  startup warm-up took the process to 7.8 GB, past pm2's 4.5 GB ceiling,
  and production restarted in a loop for a few minutes; the warm-up loads
  only the retrieval models again.

## [1.10.9] - 2026-10-11
### Fixed
- The first question after a restart no longer waits for the models to
  load: the embedding model, BM25 index and cross-encoder are loaded with
  a warm-up search during startup, before the app reports healthy, so a
  deploy's health check waits instead of a student. The first question
  after a deploy took 33s (23.5s of it retrieval) against about 8s warm.

## [1.10.8] - 2026-10-11
### Changed
- Faster reranking: the cross-encoder now scores hybrid search's best 10
  candidates (it returns 15) and reads each up to 256 tokens. On the VPS
  that took the step from 9.0s to 4.5s median with the same golden-set
  context recall (53/58), source hits (49/50) and off-topic scores. Two
  smaller rerankers were measured and rejected: MiniLM-L6 (1.9s, but
  51/58 and 47/50) and mxbai-xsmall (slower on this CPU). Settings:
  rerank_max_candidates, reranker_max_length.

## [1.10.7] - 2026-10-11
### Fixed
- A question about one module's teaching format ("What kinds of classes
  make up Computational Intelligence II?") was sometimes routed to the
  full curriculum listing, which has no class types, so the module's
  handbook entry was never added and production answered "not stated".
  The router now treats a question about one named module as a course
  lookup (3/3 on each probe question; curriculum and compulsory-course
  questions unchanged).

## [1.10.6] - 2026-10-11
### Fixed
- Questions about one course's details (contact hours, class types, how
  it is taught) were routed to the course catalogue, which does not hold
  them, and answered "the documents do not state". When the catalogue
  finds one or two courses by name, the module-handbook search that runs
  alongside is now kept and its relevant passages are added after the
  catalogue entry; listings (compulsory courses, a professor's courses,
  the curriculum) are unchanged and do not wait for it. Attribution cases
  on apodex: 3/8 -> 8/8, then 4/4 with the change below. These answers take
  a few seconds longer (the search result is awaited).
- A PDF section up to 5000 characters (every regulation section but the
  module list, nearly every module entry) is now given to the model whole,
  whichever of its chunks matched: Computational Intelligence II was
  answered "lecture only" because its exercises were in the module's
  second chunk. A section matched twice is given once. Kilo/dots on the
  catalogue and handbook cases: 12/13 -> 13/13.

## [1.10.5] - 2026-10-11
### Changed
- PDFs are chunked by section instead of by page, and every chunk starts
  with the document and section it belongs to, e.g. "[Examination
  regulations 2026 | Section 5 Examination components]" or "[Module
  handbook | wir874 - Advanced Microeconomics]". Chunks no longer cross a
  section; the running header, page numbers and table-of-contents lines
  repeated on every page are dropped. Before, a passage could start
  mid-paragraph with nothing saying what it described (the seminar-paper
  length was given as the thesis length), and module-handbook pages after
  the first never named their module. Document titles come from a new
  "title" field in sources.json. PDFs re-index once on the first restart
  (the recorded file hash carries a chunking version).
- Measured: context recall over the golden set 52/58 -> 53/58 with no
  source-hit change; answers on the 21 PDF-based cases unchanged on both
  models. New tests/eval_retrieval.py measures retrieval with no LLM calls.
### Found
- Questions about one course's details (contact hours, class types) are
  routed to the course catalogue, which does not hold them, so the module
  handbook is never searched and the answer is "not stated". Four new
  golden cases cover this; they fail until it is fixed.

## [1.10.4] - 2026-10-11
### Fixed
- "How long should my Master's thesis be?" was answered with the length
  of a seminar paper (30,000-45,000 characters, about 15-25 pages). The
  regulations' passage on seminar papers is cut so that it does not say
  what it is about, and the 2026 changes note listed the seminar-paper
  figure prominently. The thesis FAQ and the changes note now state the
  thesis length (at most 200,000 characters, about 80 pages) next to a
  plain note that the shorter figure is for seminar papers. Found by the
  weekly golden-set run on 2026-10-11 (61/64).
- Golden set: a case that forbade "10" and "20" anywhere in the answer
  also failed correct answers listing other subjects' credits (and any
  "120 ECTS"); terms can now be regular expressions, and the case only
  fails when 10 or 20 is attributed to Econometrics. The thesis-credits
  case accepts the course catalogue as a source, as it states 30 ECTS.

## [1.10.3] - 2026-10-11
### Fixed
- An exhausted OpenRouter quota no longer takes the site down. When the
  provider answers with its daily-quota 429, the call is not retried (it
  could not succeed before the next UTC day): the provider is marked
  exhausted for the day, the same question is answered by the fallback
  provider (Gemini) at once, and admins get a Telegram alert saying why.
  Per-minute limits are still retried as before. On 2026-10-10 the quota
  was used up by local evaluation runs, this server's own counter could
  not see that, and every question retried a 429 for minutes until the
  provider was switched by hand.
- The OpenRouter daily budget assumed the 50-request free tier (45) while
  the account is on the 1000-request tier, so production moved to Gemini
  after about 15 questions a day. It is now 900.
- The thesis FAQ stated general figures that contradict this programme's
  examination regulations (grading "within about eight weeks", "some
  programmes" have a colloquium, "most programmes" award 30 credits, a
  weighted mean). It now states the programme's own rules: grading within
  six weeks, a compulsory pass/fail colloquium, 30 ECTS (24 + 6), the
  2.0 rule for differing grades, and five months of writing time.
### Changed
- tests/eval_golden.py runs through the Kilo gateway by default (no key,
  paced to 180 requests an hour), so evaluation no longer spends the
  OpenRouter quota production depends on; --gateway openrouter opts back
  in with a warning. The gateway is set by openrouter_base_url; the
  OpenRouter key is never sent to another host.

## [1.10.2] - 2026-10-11
### Changed
- The tool router (which structured lookup, if any, answers a question)
  runs on dots-3-note, with apodex as its fallback; answers are still
  written by apodex. On the golden set, full runs scored 54 and 53 of 56
  against 51, 51 and 50 with apodex routing, and on the questions where
  the two models routed differently dots was right on 12 of 15 and apodex
  on none (deadline groups mixed up, exam procedures sent to the contact
  lookup, a fee question searched in the course catalogue). Routing takes
  about 1.4 seconds longer per question. Set in config.py
  (openrouter_router_model); scripts/check_llm_models.py checks it too.

## [1.10.1] - 2026-10-11
### Changed
- The examination regulations of 04.09.2026 replace the 2023 version in
  the knowledge base (MPO_AEDS_2026_EN.pdf; the 2023 file is removed so
  the two cannot contradict each other). A curated note summarises what
  changed: thesis admission now states 60 ECTS (the 2022/2023 English
  translations said "2 ECTS", against the binding German text), seminar
  papers are about 15-25 pages, and Appendix 1 drops seven modules and adds
  new electives and "Topics in ..." modules. It tells students who started
  earlier to ask the Examinations Office which version applies to them.

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
