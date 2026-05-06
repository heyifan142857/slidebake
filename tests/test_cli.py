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


def test_cli_generates_bilingual_markdown(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "slides.pdf"
    pdf.write_bytes(b"%PDF")
    out = tmp_path / "slides.md"

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

        def translate_page(self, *, page_number: int, raw_text: str) -> TranslationResult:
            return TranslationResult(f"原文\n\n{raw_text}\n\n译文\n\ntranslated {page_number}")

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
            "--bilingual",
            "--pages",
            "1-2",
        ],
    )

    assert result.exit_code == 0, result.output
    content = out.read_text(encoding="utf-8")
    assert "## 第 1 页" in content
    assert "translated 2" in content
    assert "`zh-CN` (bilingual)" in content


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
