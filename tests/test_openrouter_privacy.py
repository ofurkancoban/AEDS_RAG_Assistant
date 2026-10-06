"""Every OpenRouter call asks for providers that neither store nor train on
the prompt, unless the setting is switched off."""

from config import settings
from graph import nodes


def test_calls_deny_data_collection_by_default():
    for purpose in ("generation", "classifier"):
        body = nodes._openrouter_extra_body(purpose)
        assert body["provider"] == {"data_collection": "deny"}
        assert body["reasoning"] == nodes._OPENROUTER_REASONING[purpose]


def test_setting_can_switch_it_off(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_deny_data_collection", False)
    assert "provider" not in nodes._openrouter_extra_body("generation")
