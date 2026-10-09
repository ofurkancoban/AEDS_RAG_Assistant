"""Checks that the OpenRouter models this app is configured to use still exist.

Why this exists. OpenRouter's free models are previews that can be withdrawn
without notice. When stealth/space-bunny-alpha was, every answer kept
failing against it and falling back to the second model - silently, because
the fallback is exactly what hides a dead primary. The stale name survived
in two places that override the code default: a line in .env and a value
saved through the admin panel (RuntimeConfig). Nothing noticed for days.

What it does:
  - reads the EFFECTIVE openrouter_model / openrouter_fallback_model and
    checks each against OpenRouter's live model list;
  - reports a model line left in .env (model choice belongs to the code
    default and the admin panel; scripts/deploy.sh strips it on deploy);
  - with --fix, clears an admin-panel value naming a withdrawn model, so the
    code default applies again (only when that default itself is available);
  - alerts the admin Telegram chat about anything it found or fixed.

--fix is meant for deploy, which restarts the app afterwards: the running
server caches the effective config, so a database change made from this
separate process only takes effect after a restart. The daily run
(scripts/maintenance.py) alerts only - an admin then switches the model in
the admin panel, which applies live.

Usage:
    PYTHONPATH=. python scripts/check_llm_models.py [--fix] [--no-notify]
Exit code 1 when a configured model is still unavailable afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from config import settings

MODELS_URL = "https://openrouter.ai/api/v1/models"
FIELDS = ("openrouter_model", "openrouter_fallback_model")
ENV_KEYS = {"OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODEL"}


def available_models() -> set[str]:
    response = httpx.get(MODELS_URL, timeout=20)
    response.raise_for_status()
    return {m["id"] for m in response.json()["data"]}


def env_model_lines(env_path: Path = Path(".env")) -> list[str]:
    if not env_path.exists():
        return []
    lines = []
    for raw in env_path.read_text().splitlines():
        key = raw.split("=", 1)[0].strip()
        if key in ENV_KEYS and not raw.lstrip().startswith("#"):
            lines.append(raw.strip())
    return lines


def openrouter_in_use(config) -> bool:
    return "openrouter" in (config.llm_provider, config.daily_budget_fallback_provider)


def check(fix: bool, models: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Returns (problems still open, actions taken)."""
    from db.models import RuntimeConfig, SessionLocal
    from runtime_config import get_runtime_config, update_runtime_config

    config = get_runtime_config()
    problems: list[str] = []
    actions: list[str] = []

    for line in env_model_lines():
        problems.append(
            f".env sets '{line}', which overrides the code default - model choice belongs to "
            "config.py and the admin panel (scripts/deploy.sh removes this line on deploy)."
        )

    if not openrouter_in_use(config):
        return problems, actions

    if models is None:
        models = available_models()

    session = SessionLocal()
    try:
        row = session.get(RuntimeConfig, 1)
        stored = {field: getattr(row, field, None) if row else None for field in FIELDS}
    finally:
        session.close()

    for field in FIELDS:
        effective = getattr(config, field)
        if not effective or effective in models:
            continue
        default = getattr(settings, field)
        if fix and stored[field] == effective and default in models:
            update_runtime_config(**{field: None})
            actions.append(f"{field}: cleared the admin-panel value '{effective}' (no longer on OpenRouter); "
                           f"the code default '{default}' applies after the restart.")
            continue
        source = "admin panel" if stored[field] == effective else ".env or the code default"
        problems.append(f"{field} is '{effective}' (set via {source}), which OpenRouter no longer offers.")

    return problems, actions


def main() -> int:
    fix = "--fix" in sys.argv
    notify = "--no-notify" not in sys.argv
    try:
        problems, actions = check(fix=fix)
    except httpx.HTTPError as exc:
        # OpenRouter unreachable is not evidence a model is gone - say so and
        # don't fail a deploy over it.
        print(f"Could not reach OpenRouter to verify models: {exc}")
        return 0

    for line in actions:
        print(f"FIXED  {line}")
    for line in problems:
        print(f"PROBLEM  {line}")
    if not problems and not actions:
        print("OK  configured OpenRouter models are available.")

    if notify and (problems or actions):
        from api.telegram_bot import _notify_admins

        _notify_admins("LLM model check\n" + "\n".join(f"- {line}" for line in actions + problems))

    model_problems = [p for p in problems if not p.startswith(".env")]
    return 1 if model_problems else 0


if __name__ == "__main__":
    sys.exit(main())
