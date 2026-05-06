from pathlib import Path

from slidebake.markdown import MarkdownPage, compose_markdown, local_clean_ocr_text
from slidebake.ocr import OcrPage


def test_compose_markdown_target_language_only() -> None:
    content = compose_markdown(
        title="Deck",
        pages=[MarkdownPage(page_number=1, body="- 你好")],
        source_pdf=Path("deck.pdf"),
        target_lang="zh-CN",
    )

    assert content.startswith("# Deck\n")
    assert "> Source: `deck.pdf`" in content
    assert "## 第 1 页" in content
    assert "- 你好" in content


def test_compose_markdown_bilingual_and_error() -> None:
    content = compose_markdown(
        title="Deck",
        pages=[MarkdownPage(page_number=2, body="原文\n\n译文", error="timeout")],
        target_lang="Chinese",
        bilingual=True,
    )

    assert "`Chinese` (bilingual)" in content
    assert "## 第 2 页" in content
    assert "> 翻译失败：timeout" in content


def test_local_clean_ocr_text_handles_empty_pages() -> None:
    page = OcrPage(page_number=1, width=100, height=100, lines=())

    assert local_clean_ocr_text(page) == "本页未识别到文字。"
