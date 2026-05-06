from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ocr import OcrPage

EMPTY_PAGE_TEXT = "本页未识别到文字。"


@dataclass(frozen=True)
class MarkdownPage:
    page_number: int
    body: str
    raw_text: str = ""
    error: str | None = None


def title_from_pdf(pdf_path: Path) -> str:
    return pdf_path.stem.replace("_", " ").strip() or "slidebake output"


def local_clean_ocr_text(page: OcrPage) -> str:
    text = page.text.strip()
    return text if text else EMPTY_PAGE_TEXT


def compose_markdown(
    *,
    title: str,
    pages: list[MarkdownPage],
    source_pdf: Path | None = None,
    target_lang: str | None = None,
    bilingual: bool = False,
) -> str:
    lines: list[str] = [f"# {title}", ""]
    if source_pdf is not None:
        lines.extend([f"> Source: `{source_pdf.name}`", ""])
    if target_lang:
        mode = "bilingual" if bilingual else "target-language only"
        lines.extend([f"> Target language: `{target_lang}` ({mode})", ""])

    for page in pages:
        lines.extend([f"## 第 {page.page_number} 页", ""])
        body = page.body.strip() or EMPTY_PAGE_TEXT
        lines.append(body)
        if page.error:
            lines.extend(["", f"> LLM 处理失败：{page.error}"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
