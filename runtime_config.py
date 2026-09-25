"""Live-editable subset of settings (see config.py's Settings for the static,
restart-only ones). Backed by a single-row SQLite table (RuntimeConfig,
id=1) so changes made via the admin RAG Settings UI survive a restart.

Deliberately excludes anything that would require re-embedding the corpus
(embedding_provider, local_embedding_model) or the reranker model, which
stay config.py constants. llm_provider IS here and IS live-switchable -
graph/nodes.py's get_llm()/get_classifier_llm() re-check it on every call,
and api/rate_limit.py + llm_budget.py both derive their provider-specific
numbers from the live value too (see get_chat_limiter/get_chat_ip_limiter
and llm_budget._live_daily_budget), so a switch changes the actual model
AND its quota protection together, not just the model.
"""

from functools import lru_cache

from config import settings
from db.models import RuntimeConfig, SessionLocal

# Whitelisted Gemini chat models a live switch is actually safe/sensible
# between - both are on the free tier and need no other code changes.
ALLOWED_GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-3.6-flash"]

ALLOWED_LLM_PROVIDERS = ["ollama", "gemini", "openrouter"]


def _override(stored, fallback):
    """Falls back to the config.py default only when nothing is stored.

    Deliberately an `is None` check rather than `or`: conversation_history_window
    accepts 0 (meaning "send no prior turns"), and `or` silently turned that
    stored 0 back into the default 12 - the admin UI reported 12 right after
    saving 0, with no way to actually disable history.
    """
    return fallback if stored is None else stored


class EffectiveConfig:
    def __init__(self, row: RuntimeConfig | None):
        self.llm_provider = _override(row.llm_provider if row else None, settings.llm_provider)
        self.gemini_model = _override(row.gemini_model if row else None, settings.gemini_model)
        self.openrouter_model = _override(row.openrouter_model if row else None, settings.openrouter_model)
        self.retrieval_top_k = _override(row.retrieval_top_k if row else None, settings.retrieval_top_k)
        self.rerank_top_k = _override(row.rerank_top_k if row else None, settings.rerank_top_k)
        self.conversation_history_window = _override(
            row.conversation_history_window if row else None,
            settings.conversation_history_window,
        )
        self.system_prompt_override = row.system_prompt_override if row else None


def active_chat_model() -> str:
    """The model actually answering chat turns, against the LIVE provider
    (admin-switchable, see EffectiveConfig.llm_provider) - not the one fixed
    in .env at startup. Every caller that wants to *display* the chat model
    must go through here rather than settings.llm_provider directly, or a
    live switch away from the .env default would report a model that isn't
    actually running.
    """
    config = get_runtime_config()
    if config.llm_provider == "gemini":
        return config.gemini_model
    if config.llm_provider == "openrouter":
        return config.openrouter_model
    return settings.ollama_llm_model


@lru_cache(maxsize=1)
def _cached_effective_config() -> EffectiveConfig:
    session = SessionLocal()
    try:
        row = session.get(RuntimeConfig, 1)
        return EffectiveConfig(row)
    finally:
        session.close()


def get_runtime_config() -> EffectiveConfig:
    return _cached_effective_config()


def update_runtime_config(**fields) -> EffectiveConfig:
    """Persists the given fields (any subset of RuntimeConfig's editable
    columns) into the singleton row, creating it on first use, then
    invalidates the cache so the next get_runtime_config() call - and, since
    graph/nodes.py's cached LLM getters check gemini_model against this on
    every call, the next chat turn - picks up the change immediately."""
    session = SessionLocal()
    try:
        row = session.get(RuntimeConfig, 1)
        if row is None:
            row = RuntimeConfig(id=1)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        session.commit()
    finally:
        session.close()

    _cached_effective_config.cache_clear()
    return get_runtime_config()
