from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_ENV = "SLIDEBAKE_CONFIG"
OPENAI_API_RESPONSES = "responses"
OPENAI_API_CHAT_COMPLETIONS = "chat_completions"
OPENAI_API_VALUES = {OPENAI_API_RESPONSES, OPENAI_API_CHAT_COMPLETIONS}


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    api: str | None = None


@dataclass(frozen=True)
class SlidebakeConfig:
    openai: OpenAISettings


def default_config_path() -> Path:
    return Path.home() / ".config" / "slidebake" / "config.toml"


def load_config(config_path: Path | None = None) -> SlidebakeConfig:
    path = _resolve_config_path(config_path)
    if path is None:
        return SlidebakeConfig(openai=OpenAISettings())

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid config file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a TOML table.")

    openai_table = data.get("openai", {})
    if not isinstance(openai_table, dict):
        raise ValueError(f"Config file {path} must use an [openai] table.")

    return SlidebakeConfig(
        openai=OpenAISettings(
            api_key=_optional_string(openai_table, "api_key", path=path),
            base_url=_optional_string(openai_table, "base_url", path=path),
            model=_optional_string(openai_table, "model", path=path),
            api=normalize_openai_api(_optional_string(openai_table, "api", path=path)),
        )
    )


def resolve_openai_settings(
    *,
    config: SlidebakeConfig,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api: str | None = None,
) -> OpenAISettings:
    return OpenAISettings(
        api_key=_first_non_empty(
            api_key,
            os.environ.get("SLIDEBAKE_OPENAI_API_KEY"),
            config.openai.api_key,
            os.environ.get("OPENAI_API_KEY"),
        ),
        base_url=_first_non_empty(
            base_url,
            os.environ.get("SLIDEBAKE_OPENAI_BASE_URL"),
            config.openai.base_url,
            os.environ.get("OPENAI_BASE_URL"),
        ),
        model=_first_non_empty(
            model,
            os.environ.get("SLIDEBAKE_OPENAI_MODEL"),
            config.openai.model,
        ),
        api=normalize_openai_api(
            _first_non_empty(
                api,
                os.environ.get("SLIDEBAKE_OPENAI_API"),
                config.openai.api,
            )
        ),
    )


def normalize_openai_api(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower().replace("-", "_").replace(".", "_")
    aliases = {
        "chat": OPENAI_API_CHAT_COMPLETIONS,
        "chat_completion": OPENAI_API_CHAT_COMPLETIONS,
        "chat_completions": OPENAI_API_CHAT_COMPLETIONS,
        "responses": OPENAI_API_RESPONSES,
        "response": OPENAI_API_RESPONSES,
    }
    api = aliases.get(normalized, normalized)
    if api not in OPENAI_API_VALUES:
        expected = ", ".join(sorted(OPENAI_API_VALUES))
        raise ValueError(f"OpenAI API mode must be one of: {expected}.")
    return api


def _resolve_config_path(config_path: Path | None) -> Path | None:
    if config_path is not None:
        return _existing_explicit_path(config_path)

    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        return _existing_explicit_path(Path(env_path))

    path = default_config_path()
    return path if path.exists() else None


def _existing_explicit_path(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.exists():
        raise FileNotFoundError(f"Config file not found: {expanded}")
    if not expanded.is_file():
        raise ValueError(f"Config path is not a file: {expanded}")
    return expanded


def _optional_string(table: dict[str, Any], key: str, *, path: Path) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Config value [openai].{key} in {path} must be a string.")
    return value.strip() or None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None
