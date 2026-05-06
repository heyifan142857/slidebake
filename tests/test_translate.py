from __future__ import annotations

from dataclasses import dataclass

from slidebake.config import OPENAI_API_CHAT_COMPLETIONS
from slidebake.translate import OpenAITranslator


@dataclass
class FakeResponse:
    output_text: str


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.failures_before_success = 0

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures_before_success:
            raise RuntimeError("temporary failure")
        return FakeResponse("翻译结果")


@dataclass
class FakeChatMessage:
    content: str


@dataclass
class FakeChatChoice:
    message: FakeChatMessage


@dataclass
class FakeChatResponse:
    choices: list[FakeChatChoice]


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeChatResponse:
        self.calls.append(kwargs)
        return FakeChatResponse([FakeChatChoice(FakeChatMessage("chat 翻译结果"))])


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeChatCompletions()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()
        self.chat = FakeChat()


def test_translator_calls_responses_api_with_prompt() -> None:
    client = FakeClient()
    translator = OpenAITranslator(
        target_lang="zh-CN",
        model="gpt-test",
        client=client,
        retry_base_seconds=0,
    )

    result = translator.translate_page(page_number=3, raw_text="Functional requirements")

    assert result.body == "翻译结果"
    assert result.error is None
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    messages = call["input"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "developer"
    assert "zh-CN" in messages[1]["content"]
    assert "Functional requirements" in messages[1]["content"]


def test_translator_calls_chat_completions_for_compatible_api() -> None:
    client = FakeClient()
    translator = OpenAITranslator(
        target_lang="zh-CN",
        model="compatible-model",
        api=OPENAI_API_CHAT_COMPLETIONS,
        client=client,
        retry_base_seconds=0,
    )

    result = translator.translate_page(page_number=2, raw_text="Architecture overview")

    assert result.body == "chat 翻译结果"
    call = client.chat.completions.calls[0]
    assert call["model"] == "compatible-model"
    messages = call["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Architecture overview" in messages[1]["content"]


def test_translator_uses_env_model_when_model_not_explicit(monkeypatch) -> None:
    monkeypatch.setenv("SLIDEBAKE_OPENAI_MODEL", "gpt-env")
    client = FakeClient()
    translator = OpenAITranslator(
        target_lang="zh-CN",
        client=client,
        retry_base_seconds=0,
    )

    translator.translate_page(page_number=1, raw_text="text")

    assert client.responses.calls[0]["model"] == "gpt-env"


def test_translator_retries_then_succeeds() -> None:
    client = FakeClient()
    client.responses.failures_before_success = 1
    translator = OpenAITranslator(
        target_lang="Chinese",
        client=client,
        retry_base_seconds=0,
    )

    result = translator.translate_page(page_number=1, raw_text="text")

    assert result.body == "翻译结果"
    assert len(client.responses.calls) == 2


def test_translator_returns_raw_text_on_persistent_failure() -> None:
    client = FakeClient()
    client.responses.failures_before_success = 10
    translator = OpenAITranslator(
        target_lang="Chinese",
        client=client,
        max_retries=2,
        retry_base_seconds=0,
    )

    result = translator.translate_page(page_number=1, raw_text="raw")

    assert result.body == "raw"
    assert "temporary failure" in (result.error or "")
