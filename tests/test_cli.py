from pathlib import Path

from typer.testing import CliRunner

import slidebake.cli as cli
from slidebake.cli import app
from slidebake.config import OpenAISettings
from slidebake.ocr import OcrLine, OcrPage
from slidebake.pdf import RenderedPage
from slidebake.translate import TranslationResult

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "slide-deck PDFs" in result.output


def test_cli_check_key_uses_config_without_pdf(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "slidebake.toml"
    config.write_text(
        "\n".join(
            [
                "[openai]",
                'api_key = "sk-test-123456"',
                'base_url = "https://api.example.test/v1"',
                'model = "compatible-model"',
                'api = "chat_completions"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLIDEBAKE_OPENAI_API_KEY", raising=False)

    result = runner.invoke(app, ["--check-key", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert "API key found" in result.output
    assert "sk-t...3456" in result.output
    assert "sk-test-123456" not in result.output
    assert "https://api.example.test/v1" in result.output
    assert "compatible-model" in result.output
    assert "chat_completions" in result.output


def test_cli_checkkey_alias_reports_missing_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLIDEBAKE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLIDEBAKE_CONFIG", raising=False)

    result = runner.invoke(app, ["--checkkey"])

    assert result.exit_code == 1
    assert "API key missing" in result.output
    assert "[openai].api_key" in result.output


def test_cli_generates_bilingual_markdown(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "slides.pdf"
    pdf.write_bytes(b"%PDF")
    out = tmp_path / "slides_zh-CN_bilingual.md"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "page_count", lambda _path: 2)
    monkeypatch.setattr(
        cli,
        "render_pages",
        lambda _pdf, pages, output_dir, dpi: [
            RenderedPage(page, output_dir / f"page-{page}.png", 100, 100)
            for page in pages
        ],
    )

    class FakeOcrRunner:
        def recognize(self, _image_path: Path, page_number: int) -> OcrPage:
            return OcrPage(
                page_number=page_number,
                width=100,
                height=100,
                lines=(OcrLine(f"raw {page_number}", 1, 0, 0, 10, 10),),
            )

    class FakeTranslator:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def clean_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            return TranslationResult(f"cleaned {page_number}: {raw_text}")

        def translate_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            return TranslationResult(f"原文\n\n{raw_text}\n\n译文\n\ntranslated {page_number}")

    monkeypatch.setattr(cli, "OcrRunner", FakeOcrRunner)
    monkeypatch.setattr(cli, "OpenAITranslator", FakeTranslator)

    result = runner.invoke(
        app,
        [
            str(pdf),
            "--target-lang",
            "zh-CN",
            "--bilingual",
            "--pages",
            "1-2",
        ],
    )

    assert result.exit_code == 0, result.output
    content = out.read_text(encoding="utf-8")
    assert "## 第 1 页" in content
    assert "cleaned 2: raw 2" in content
    assert "translated 2" in content
    assert "`zh-CN` (bilingual)" in content


def test_cli_cleans_markdown_without_translation(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "slides.pdf"
    pdf.write_bytes(b"%PDF")
    out = tmp_path / "slides.md"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "page_count", lambda _path: 1)
    monkeypatch.setattr(
        cli,
        "render_pages",
        lambda _pdf, pages, output_dir, dpi: [
            RenderedPage(page, output_dir / f"page-{page}.png", 100, 100)
            for page in pages
        ],
    )

    class FakeOcrRunner:
        def recognize(self, _image_path: Path, page_number: int) -> OcrPage:
            return OcrPage(
                page_number=page_number,
                width=100,
                height=100,
                lines=(OcrLine("Soffware archifecture", 1, 0, 0, 10, 10),),
            )

    class FakeTranslator:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def clean_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            assert raw_text == "Soffware archifecture"
            return TranslationResult(f"cleaned page {page_number}")

        def translate_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            raise AssertionError("translation should not run without --target-lang")

    monkeypatch.setattr(cli, "OcrRunner", FakeOcrRunner)
    monkeypatch.setattr(cli, "OpenAITranslator", FakeTranslator)

    result = runner.invoke(app, [str(pdf)])

    assert result.exit_code == 0, result.output
    content = out.read_text(encoding="utf-8")
    assert "cleaned page 1" in content
    assert "Target language" not in content


def test_cli_requires_openai_key_for_cleanup_without_translation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf = tmp_path / "slides.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLIDEBAKE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLIDEBAKE_CONFIG", raising=False)

    result = runner.invoke(app, [str(pdf)])

    assert result.exit_code == 1
    assert "LLM cleanup" in result.output
    assert "every run" in result.output


def test_default_output_path_reflects_translation_mode(tmp_path: Path) -> None:
    pdf = tmp_path / "deck.v1.pdf"

    assert (
        cli._default_output_path(pdf, target_lang=None, bilingual=False)
        == tmp_path / "deck.v1.md"
    )
    assert (
        cli._default_output_path(pdf, target_lang="zh-CN", bilingual=False)
        == tmp_path / "deck.v1_zh-CN_translated.md"
    )
    assert (
        cli._default_output_path(pdf, target_lang="zh-CN", bilingual=True)
        == tmp_path / "deck.v1_zh-CN_bilingual.md"
    )
    assert (
        cli._default_output_path(pdf, target_lang="Chinese (Simplified)", bilingual=True)
        == tmp_path / "deck.v1_Chinese-Simplified_bilingual.md"
    )


def test_cli_uses_configured_openai_settings(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "slides.pdf"
    pdf.write_bytes(b"%PDF")
    out = tmp_path / "slides.md"
    config = tmp_path / "slidebake.toml"
    config.write_text(
        "\n".join(
            [
                "[openai]",
                'api_key = "config-key"',
                'base_url = "https://api.example.test/v1"',
                'model = "compatible-model"',
                'api = "chat_completions"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "page_count", lambda _path: 1)
    monkeypatch.setattr(
        cli,
        "render_pages",
        lambda _pdf, pages, output_dir, dpi: [
            RenderedPage(page, output_dir / f"page-{page}.png", 100, 100)
            for page in pages
        ],
    )

    class FakeOcrRunner:
        def recognize(self, _image_path: Path, page_number: int) -> OcrPage:
            return OcrPage(
                page_number=page_number,
                width=100,
                height=100,
                lines=(OcrLine("raw", 1, 0, 0, 10, 10),),
            )

    captured_settings: list[OpenAISettings] = []

    class FakeTranslator:
        def __init__(self, **kwargs: object) -> None:
            captured_settings.append(
                OpenAISettings(
                    api_key=kwargs.get("api_key"),
                    base_url=kwargs.get("base_url"),
                    model=kwargs.get("model"),
                    api=kwargs.get("api"),
                )
            )

        def clean_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            return TranslationResult(f"cleaned {page_number}: {raw_text}")

        def translate_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            return TranslationResult(f"translated {page_number}: {raw_text}")

    monkeypatch.setattr(cli, "OcrRunner", FakeOcrRunner)
    monkeypatch.setattr(cli, "OpenAITranslator", FakeTranslator)

    result = runner.invoke(
        app,
        [
            str(pdf),
            "-o",
            str(out),
            "--target-lang",
            "zh-CN",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_settings == [
        OpenAISettings(
            api_key="config-key",
            base_url="https://api.example.test/v1",
            model="compatible-model",
            api="chat_completions",
        )
    ]


def test_cli_refuses_existing_output(tmp_path: Path) -> None:
    pdf = tmp_path / "slides.pdf"
    out = tmp_path / "slides.md"
    pdf.write_bytes(b"%PDF")
    out.write_text("exists", encoding="utf-8")

    result = runner.invoke(app, [str(pdf), "-o", str(out)])

    assert result.exit_code == 1
    assert "already exists" in result.output
