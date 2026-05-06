from __future__ import annotations

from pathlib import Path

import pytest

from slidebake.config import (
    OPENAI_API_CHAT_COMPLETIONS,
    OPENAI_API_RESPONSES,
    OpenAISettings,
    SlidebakeConfig,
    default_config_path,
    load_config,
    normalize_openai_api,
    resolve_openai_settings,
)


def test_loads_home_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = default_config_path()
    assert config_path == tmp_path / ".config" / "slidebake" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "[openai]",
                'api_key = "config-key"',
                'base_url = "https://api.example.test/v1"',
                'model = "model-from-config"',
                'api = "chat_completions"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config()

    assert config.openai.api_key == "config-key"
    assert config.openai.base_url == "https://api.example.test/v1"
    assert config.openai.model == "model-from-config"
    assert config.openai.api == OPENAI_API_CHAT_COMPLETIONS


def test_resolve_openai_settings_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLIDEBAKE_OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("SLIDEBAKE_OPENAI_BASE_URL", "https://env.example.test/v1")
    monkeypatch.setenv("SLIDEBAKE_OPENAI_MODEL", "env-model")
    monkeypatch.setenv("SLIDEBAKE_OPENAI_API", "responses")
    config = SlidebakeConfig(
        openai=OpenAISettings(
            api_key="config-key",
            base_url="https://config.example.test/v1",
            model="config-model",
            api=OPENAI_API_CHAT_COMPLETIONS,
        )
    )

    settings = resolve_openai_settings(
        config=config,
        api_key="cli-key",
        base_url="https://cli.example.test/v1",
        model="cli-model",
        api="chat",
    )

    assert settings == OpenAISettings(
        api_key="cli-key",
        base_url="https://cli.example.test/v1",
        model="cli-model",
        api=OPENAI_API_CHAT_COMPLETIONS,
    )


def test_config_api_key_beats_generic_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "generic-openai-key")
    config = SlidebakeConfig(openai=OpenAISettings(api_key="config-key"))

    settings = resolve_openai_settings(config=config)

    assert settings.api_key == "config-key"


def test_normalize_openai_api_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match=OPENAI_API_RESPONSES):
        normalize_openai_api("assistants")
