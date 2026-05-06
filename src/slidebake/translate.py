from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

from .config import (
    OPENAI_API_CHAT_COMPLETIONS,
    OPENAI_API_RESPONSES,
    normalize_openai_api,
)
from .markdown import EMPTY_PAGE_TEXT

DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_API = OPENAI_API_RESPONSES


class ResponsesClient(Protocol):
    class responses(Protocol):  # pragma: no cover - structural typing only
        @staticmethod
        def create(**kwargs: object) -> object: ...


@dataclass(frozen=True)
class TranslationResult:
    body: str
    error: str | None = None


class OpenAITranslator:
    def __init__(
        self,
        *,
        target_lang: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        api: str | None = None,
        bilingual: bool = False,
        client: object | None = None,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
    ) -> None:
        self.target_lang = target_lang
        self.model = model or os.environ.get("SLIDEBAKE_OPENAI_MODEL") or DEFAULT_MODEL
        self.api_key = api_key
        self.base_url = base_url
        self.api = normalize_openai_api(api) or DEFAULT_OPENAI_API
        self.bilingual = bilingual
        self.client = client
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds

    def translate_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
        raw_text = raw_text.strip()
        if not raw_text:
            return TranslationResult(EMPTY_PAGE_TEXT)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                text = self._request_translation(page_number=page_number, raw_text=raw_text)
                return TranslationResult(text.strip())
            except Exception as exc:  # noqa: BLE001 - preserve page output on API failures
                last_error = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_base_seconds * (2**attempt))

        message = str(last_error) if last_error else "unknown OpenAI error"
        return TranslationResult(raw_text, error=message)

    def _client(self) -> object:
        if self.client is None:
            from openai import OpenAI

            kwargs: dict[str, str] = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = OpenAI(**kwargs)
        return self.client

    def _request_translation(self, *, page_number: int, raw_text: str) -> str:
        if self.api == OPENAI_API_CHAT_COMPLETIONS:
            response = self._client().chat.completions.create(
                model=self.model,
                messages=self._chat_messages(page_number=page_number, raw_text=raw_text),
            )
            text = _chat_completion_text(response)
        else:
            response = self._client().responses.create(
                model=self.model,
                input=self._input_messages(page_number=page_number, raw_text=raw_text),
            )
            text = getattr(response, "output_text", None)

        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI response did not include output text.")
        return text

    def _input_messages(self, *, page_number: int, raw_text: str) -> list[dict[str, str]]:
        developer, user = self._prompt_parts(page_number=page_number, raw_text=raw_text)
        return [
            {"role": "developer", "content": developer},
            {"role": "user", "content": user},
        ]

    def _chat_messages(self, *, page_number: int, raw_text: str) -> list[dict[str, str]]:
        developer, user = self._prompt_parts(page_number=page_number, raw_text=raw_text)
        return [
            {"role": "system", "content": developer},
            {"role": "user", "content": user},
        ]

    def _prompt_parts(self, *, page_number: int, raw_text: str) -> tuple[str, str]:
        mode = (
            "Return bilingual Markdown: first a section titled `原文`, then a section "
            f"titled `{self.target_lang}`, preserving the same page-level meaning."
            if self.bilingual
            else f"Return only polished Markdown in {self.target_lang}."
        )
        developer = (
            "You convert OCR output from slide-deck PDFs into clean page-level Markdown. "
            "Correct obvious OCR noise using context, preserve bullet lists and tables, "
            "ignore tiny neighboring-slide preview text from slide transitions, and do "
            "not invent content that is not supported by the OCR."
        )
        user = (
            f"Page {page_number} OCR text:\n\n"
            f"{raw_text}\n\n"
            f"{mode}\n"
            "Keep the output concise and suitable for study notes."
        )
        return developer, user


def _chat_completion_text(response: object) -> str | None:
    choices = _get_value(response, "choices")
    if not choices:
        return None
    message = _get_value(choices[0], "message")
    content = _get_value(message, "content")
    return content if isinstance(content, str) else None


def _get_value(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def require_openai_key_for_translation(
    target_lang: str | None,
    *,
    api_key: str | None = None,
) -> None:
    if target_lang and not api_key and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "An OpenAI API key is required when --target-lang is provided. "
            "Set it in ~/.config/slidebake/config.toml, pass --openai-api-key, export "
            "SLIDEBAKE_OPENAI_API_KEY, or omit --target-lang to run local OCR only."
        )
