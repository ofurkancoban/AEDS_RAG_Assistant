# AEDS RAG Assistant

A RAG-based chat assistant that answers student questions about a university
master's programme (curriculum, admission requirements, deadlines, exam
rules, course descriptions) from the programme's own official documents -
never from the model's general knowledge. Answers are grounded, cited, and
refuse outright when the documents don't cover a question, instead of
guessing. Students chat anonymously; staff manage the document corpus and
review user-submitted corrections from an admin panel.

![AEDS RAG architecture](docs/architecture.png)

<sub>Regenerate with `python docs/generate_architecture.py` (source: `docs/architecture.svg`).</sub>

## How it works

- **Two answer paths.** An LLM router sends exact-fact questions (deadlines,
  courses, curriculum, contacts) to structured SQL lookups, and everything
  else to hybrid document search (vector + keyword, fused and reranked).
- **Relevance gate.** A cross-encoder reranker's confidence score decides
  whether the retrieved material actually answers the question - below
  threshold, the assistant says so instead of generating from weak matches.
- **Admin-reviewed corpus.** Anyone can suggest a correction from the chat
  UI; nothing reaches the live corpus - or a second student - until staff
  approve it.
- **Auto-flagged corrections.** A local classifier notices when a chat
  message asserts a correction or new fact and queues it for review
  automatically, without the user needing to click anything.
- **German and English**, answered natively either way.
- **Semantic answer cache**, so a repeated question is served instantly
  without re-running the pipeline.
- **Telegram integration**: the same review queues (source changes,
  submissions, pending answers), with Approve/Reject buttons, from a phone.

Design rationale, measured performance numbers, and deployment specifics
live in [`docs/technical-reference.md`](docs/technical-reference.md) and
[`docs/deployment.md`](docs/deployment.md) - this file stays a quick
overview.

## Tech stack

**Backend** - Python, [FastAPI](https://fastapi.tiangolo.com), [LangGraph](https://langchain-ai.github.io/langgraph/)
for the answer pipeline as an explicit state graph, SQLAlchemy + SQLite for
everything that must be exact (courses, deadlines, accounts, review queues),
a LangGraph SQLite checkpointer for conversation memory.

**Retrieval** - [Chroma](https://www.trychroma.com) for vector storage,
BM25 for keyword search, fused and reranked with a cross-encoder - hybrid
search consistently finds what pure vector similarity alone misses.

**Models**, all swappable live from the admin panel:
- Embeddings: `BAAI/bge-large-en-v1.5` (local, `sentence-transformers`)
- Reranker: `BAAI/bge-reranker-base` (local cross-encoder)
- Chat/generation: local [Ollama](https://ollama.com) by default, or
  Gemini / OpenRouter as cloud alternatives
- Contribution classifier: [Laya](https://huggingface.co/convaiinnovations/laya)
  (local, no LLM call needed for the common case)

**Frontend** - React + TypeScript, Vite, Tailwind CSS.

**Ops** - nginx, pm2, a Telegram bot for admin notifications and a second
student-facing chat surface, scheduled maintenance/backup/source-refresh
jobs via cron.

## Quick start

Prerequisites: Python 3.11+, Node 18+, and [Ollama](https://ollama.com)
running locally (`ollama pull ministral-3:3b`) - no API key needed for the
default configuration.

```bash
# backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload
```

```bash
# frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and start chatting - no login required. Each
visitor gets their own anonymous session; the "Log in" button in the corner
is for staff only. The first account created via `/auth/register` becomes
the admin, and that endpoint then closes permanently.

## Ingesting documents

Supported formats: PDF, Word, Excel, PowerPoint, HTML, CSV, Markdown, plain
text. Drop files into `data/documents/` and (re)start the backend - it
scans that folder on startup and embeds anything new or changed, tracked by
content hash so unchanged files are skipped. Admins can also upload
directly from the admin panel. A source whose content expires on a known
date (e.g. application deadlines, re-published every intake) declares
`valid_until` in `data/documents/sources.json` and gets flagged once that
date passes, rather than silently presenting a closed cycle as current.

## Testing

```bash
pytest                        # fast API/unit suite, no model needed
python -m tests.eval_golden   # real answer-quality eval, needs Ollama + corpus
```

See [`docs/technical-reference.md`](docs/technical-reference.md#testing)
for what each suite actually covers and how to grow the eval set from real
admin review decisions.
