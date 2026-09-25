from pathlib import Path

from pydantic_settings import BaseSettings


DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    base_dir: Path = Path(__file__).resolve().parent

    # "production" enables fail-fast startup checks (see below) that would
    # otherwise get in the way of quick local development - e.g. refusing to
    # start with the placeholder JWT secret.
    environment: str = "development"

    sqlite_path: Path = base_dir / "data" / "sqlite" / "app.db"
    checkpointer_sqlite_path: Path = base_dir / "data" / "sqlite" / "checkpoints.db"
    chroma_persist_dir: Path = base_dir / "data" / "chroma"
    documents_dir: Path = base_dir / "data" / "documents"

    ollama_base_url: str = "http://localhost:11434"
    # Measured on the 44-case golden set (tests/eval_golden.py), all three
    # served through this same pipeline:
    #   ministral-3:3b      43/44, 33.1s/case, 3.0 GB, router 8/8
    #   LFM2.5-2.6B (GGUF)  28/44, 19.1s/case, 1.7 GB, router 7/8
    #   qwen2.5:7b-instruct not completed - 4.7 GB thrashed a 16 GB dev machine
    # LFM2.5 is faster and smaller but calls tools for questions that should
    # fall through to document search (answering "how many resits?" with the
    # examinations office contact, summing courses for a component's ECTS
    # target), which shows up as confidently wrong answers rather than
    # refusals. Ministral 3B is the default on that basis.
    ollama_llm_model: str = "ministral-3:3b"
    # bge-large is BAAI/bge-large-en-v1.5 (English-only, 1024-dim) served via
    # Ollama - only used when embedding_provider=ollama (see below).
    ollama_embedding_model: str = "bge-large"

    # Which provider serves the chat/classifier LLM: "gemini" (API) or
    # "ollama" (local). Local is the default: it removes the per-day request
    # quota that repeatedly blocked both the app and the eval suite, and keeps
    # student questions off a third-party service. The cost is latency - see
    # ollama_llm_model for measured per-case timings, and note those were taken
    # on Apple Silicon with GPU acceleration, so a CPU-only VPS will be slower.
    llm_provider: str = "ollama"
    gemini_api_key: str = ""
    # gemini-3.6-flash (frontier-tier) has a very small free-tier daily quota
    # (20 requests/day) - impractical for a chat app making multiple LLM calls
    # per turn (tool-router + generation [+ contribution classifier]).
    # gemini-3.1-flash-lite has a much more generous free tier (~1500
    # requests/day) and is the practical default for this project.
    gemini_model: str = "gemini-3.1-flash-lite"

    # llm_provider="openrouter": OpenRouter is OpenAI-API-compatible (see
    # langchain_openai.ChatOpenAI usage in graph/nodes.py), and its ":free"
    # suffixed models cost nothing - but the free tier is small: 20
    # requests/minute, and only 50/day unless the account has purchased at
    # least $10 in credits at some point (then 1000/day). A chat turn can
    # spend 2-3 requests (tool router + generation [+ contribution
    # classifier]), so the no-credits tier realistically covers roughly
    # 15-25 real questions per day - measure your own account's tier via
    # GET https://openrouter.ai/api/v1/key before relying on this for more
    # than a handful of concurrent users.
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-31b-it:free"

    # Ceiling on LLM requests issued per calendar day, enforced in-app (see
    # llm_budget.py). 0 means no ceiling; leave it at -1 to derive one from the
    # provider (see effective_daily_llm_budget).
    #
    # This exists to stay under a provider's own daily quota: better to stop
    # with a clear message while some allowance remains than to discover the
    # limit as raw 429s mid-answer. That reasoning only applies to a metered
    # provider - a local model has no external quota to run out of, and
    # applying a request ceiling there just takes the assistant offline for the
    # rest of the day at no saving.
    daily_llm_call_budget: int = -1

    # Which provider serves embeddings: "local" (sentence-transformers, no
    # API/network call, no rate limit - see local_embedding_model), "gemini"
    # (API, gemini-embedding-001, 3072-dim) or "ollama" (bge-large via Ollama,
    # 1024-dim). "local" is the default: embeddings run on every retrieval
    # call (unlike the LLM, which runs once or twice per chat turn), so a
    # small local model avoids per-query API cost/latency and - as
    # experienced first-hand - the free tier's per-minute quota getting
    # blown through during a bulk re-ingest of the whole document corpus.
    # Changing this changes the vector dimension, so switching requires
    # wiping and re-ingesting data/chroma (see README).
    embedding_provider: str = "local"
    # BAAI/bge-large-en-v1.5: English-only, 1024-dim, ~335M params - stronger
    # retrieval quality than bge-small on MTEB benchmarks (this project has
    # already validated bge-large's real-world quality edge over a weaker
    # embedding model firsthand, via Ollama, earlier on). ~10x bge-small's
    # compute cost, but on this project's small (few-hundred-chunk) corpus
    # that's still a matter of seconds, especially with the MPS/CUDA
    # auto-detection already used for the reranker (see db/reranker.py) -
    # so there's little reason to leave quality on the table for speed here.
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Comma-separated browser origins allowed to call this API, e.g.
    # "https://aeds.example.edu". Localhost dev ports are additionally allowed
    # by regex outside production (see api/main.py). Must be set before
    # deploying: with many users on a real domain, an origin that is not
    # listed here simply cannot reach the backend from the browser.
    cors_allow_origins: str = "http://localhost:5173,http://localhost:5174"

    # Note: there is deliberately no proxy setting here. Rate limiting is keyed
    # by client IP, and the address it uses is resolved by uvicorn's
    # --forwarded-allow-ips, not by this app - see api/rate_limit.py's
    # client_ip for what to set it to when deploying behind nginx/Caddy.

    chunk_size: int = 1500
    chunk_overlap: int = 200
    # Pool size fetched from hybrid (vector + BM25) search, before reranking
    # narrows it down to rerank_top_k for the LLM.
    retrieval_top_k: int = 10
    # Cross-encoder reranker model (BAAI/bge-reranker-large via
    # sentence-transformers) that re-scores the retrieval_top_k pool for
    # actual query relevance - a plain embedding similarity/BM25 union misses
    # fine-grained distinctions (e.g. which specific exam rule or ECTS figure
    # among several similar-looking chunks actually answers the question).
    reranker_model: str = "BAAI/bge-reranker-base"
    # Minimum cross-encoder score the best retrieved chunk must reach before
    # the pipeline will answer from documents at all. Below it, retrieval is
    # treated as having found nothing relevant.
    #
    # Measured on this corpus (top rerank score per question):
    #   answerable questions      0.698 - 0.996
    #   questions it cannot answer 0.000 - 0.003
    # The two classes separate by ~200x, so the exact value matters little.
    # Chosen near the noise floor rather than midway: a threshold that is too
    # high silently refuses real questions, which is worse and harder to
    # notice than letting a borderline one through, and the sample behind
    # these bounds is only five questions per side.
    retrieval_relevance_threshold: float = 0.05
    # Briefly bumped to 6 to work around a chunk-quality problem (a messy,
    # unstructured source document ranked its own correct-answer chunk too
    # low), but that just traded one failure for another: it let more
    # generic-source noise back into context for other queries and broke a
    # previously-stable case. Reverted to 4 once the actual root cause (the
    # source document itself, not the pool size) was fixed - the same
    # question's correct chunk ranks #1 with a clean source and this setting.
    rerank_top_k: int = 4
    # Caps how many prior turns are sent to the LLM alongside the latest
    # question - without this, a long-running conversation thread would keep
    # growing its message history unboundedly and eventually overflow num_ctx,
    # silently truncating context in an unpredictable way rather than a
    # controlled, recent-first window.
    conversation_history_window: int = 12

    # Telegram bot used by scripts/source_refresh.py to notify an admin when a
    # source page changed, instead of that only being visible on a visit to
    # the admin panel. Both empty (the default) means the script logs the
    # finding and skips the notification rather than erroring - nightly cron
    # jobs shouldn't fail because notifications aren't configured.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def effective_daily_llm_budget(self) -> int:
        """Requests allowed per day, 0 meaning unlimited.

        Derived from the provider unless daily_llm_call_budget is set
        explicitly. The observed free-tier cap for gemini-3.1-flash-lite was
        500/day, so 450 leaves margin for the retries _with_resilience makes
        (which also spend quota). openrouter's ":free" models are capped at
        50/day with no purchased credits (see openrouter_api_key's
        docstring) - 45 leaves the same retry margin; if the account has
        bought credits and is really on the 1000/day tier, set
        daily_llm_call_budget explicitly rather than relying on this
        conservative default. Local models are unmetered - their real
        constraint is CPU throughput, which the per-client rate limiter and
        the hardware already bound.
        """
        if self.daily_llm_call_budget >= 0:
            return self.daily_llm_call_budget
        if self.llm_provider == "gemini":
            return 450
        if self.llm_provider == "openrouter":
            return 45
        return 0

    class Config:
        env_file = ".env"


settings = Settings()

if settings.environment == "production" and settings.jwt_secret == DEFAULT_JWT_SECRET:
    raise RuntimeError(
        "Refusing to start with environment=production and the default jwt_secret. "
        "Set a real JWT_SECRET (e.g. in .env) before deploying - tokens signed with "
        "the placeholder secret would let anyone forge an admin session."
    )

if settings.llm_provider == "gemini" and not settings.gemini_api_key:
    raise RuntimeError(
        "llm_provider is 'gemini' but gemini_api_key is not set. Add "
        "GEMINI_API_KEY=<your key> to .env (get one at "
        "https://aistudio.google.com/apikey), or set LLM_PROVIDER=ollama to "
        "use the local model instead."
    )

if settings.llm_provider == "openrouter" and not settings.openrouter_api_key:
    raise RuntimeError(
        "llm_provider is 'openrouter' but openrouter_api_key is not set. Add "
        "OPENROUTER_API_KEY=<your key> to .env (get one at "
        "https://openrouter.ai/keys), or set LLM_PROVIDER=ollama to use the "
        "local model instead."
    )

for path in (settings.sqlite_path.parent, settings.chroma_persist_dir, settings.documents_dir):
    path.mkdir(parents=True, exist_ok=True)
