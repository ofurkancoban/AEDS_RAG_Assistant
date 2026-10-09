"""scripts/check_llm_models.py: a withdrawn OpenRouter model must not keep
answering silently through the fallback, and an admin-panel value naming one
is cleared on deploy so the code default applies again."""

import pytest

from config import settings
from runtime_config import get_runtime_config, update_runtime_config
from scripts import check_llm_models as checker

# Kept before the autouse fixture below stubs it out for every other test.
_real_env_model_lines = checker.env_model_lines

AVAILABLE = {settings.openrouter_model, settings.openrouter_fallback_model, "some/other-model:free"}


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    monkeypatch.setattr(checker, "env_model_lines", lambda *a, **k: [])


def test_env_model_lines_finds_only_active_model_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "OPENROUTER_API_KEY=secret\n"
        "OPENROUTER_MODEL=stealth/old:free\n"
        "# OPENROUTER_FALLBACK_MODEL=commented/out\n"
        "LLM_PROVIDER=openrouter\n"
    )
    assert _real_env_model_lines(env) == ["OPENROUTER_MODEL=stealth/old:free"]


def test_dead_admin_value_is_cleared_with_fix():
    update_runtime_config(llm_provider="openrouter", openrouter_model="stealth/withdrawn:free")

    problems, actions = checker.check(fix=True, models=AVAILABLE)

    assert problems == []
    assert len(actions) == 1 and "stealth/withdrawn:free" in actions[0]
    assert get_runtime_config().openrouter_model == settings.openrouter_model


def test_without_fix_it_reports_and_changes_nothing():
    update_runtime_config(llm_provider="openrouter", openrouter_fallback_model="gone/fallback:free")

    problems, actions = checker.check(fix=False, models=AVAILABLE)

    assert actions == []
    assert len(problems) == 1 and "openrouter_fallback_model" in problems[0] and "admin panel" in problems[0]
    assert get_runtime_config().openrouter_fallback_model == "gone/fallback:free"


def test_a_valid_admin_choice_is_left_alone():
    update_runtime_config(llm_provider="openrouter", openrouter_model="some/other-model:free")

    problems, actions = checker.check(fix=True, models=AVAILABLE)

    assert (problems, actions) == ([], [])
    assert get_runtime_config().openrouter_model == "some/other-model:free"


def test_not_cleared_when_the_default_is_gone_too():
    update_runtime_config(llm_provider="openrouter", openrouter_model="stealth/withdrawn:free")

    problems, actions = checker.check(fix=True, models={"unrelated/model:free"})

    assert actions == []
    assert any("openrouter_model" in p for p in problems)
    assert get_runtime_config().openrouter_model == "stealth/withdrawn:free"


def test_skipped_when_openrouter_is_not_in_use():
    update_runtime_config(
        llm_provider="ollama",
        daily_budget_fallback_provider="gemini",
        openrouter_model="stealth/withdrawn:free",
    )

    assert checker.check(fix=True, models=set()) == ([], [])


def test_an_env_model_line_is_reported(monkeypatch):
    monkeypatch.setattr(checker, "env_model_lines", lambda *a, **k: ["OPENROUTER_MODEL=stealth/old:free"])
    update_runtime_config(llm_provider="ollama", daily_budget_fallback_provider="gemini")

    problems, _ = checker.check(fix=False, models=set())

    assert len(problems) == 1 and problems[0].startswith(".env")
