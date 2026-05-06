from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from . import __version__
from .markdown import (
    MarkdownPage,
    compose_markdown,
    local_clean_ocr_text,
    title_from_pdf,
    write_markdown,
)
from .ocr import OcrRunner
from .pdf import page_count, parse_page_range, render_pages
from .translate import OpenAITranslator, require_openai_key_for_translation

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Bake slide-deck PDFs into page-by-page Markdown.",
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"slidebake {__version__}")
        raise typer.Exit()


@app.command(help="Bake slide-deck PDFs into page-by-page Markdown.")
def main(
    input_pdf: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="PDF exported from a slide deck.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Markdown output path."),
    ] = None,
    target_lang: Annotated[
        str | None,
        typer.Option("--target-lang", help="Translate/clean output into this language."),
    ] = None,
    bilingual: Annotated[
        bool,
        typer.Option("--bilingual", help="Include OCR source text plus target-language output."),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help=(
                "OpenAI model for translation/cleanup. Defaults to "
                "SLIDEBAKE_OPENAI_MODEL or gpt-5.4-mini."
            ),
        ),
    ] = None,
    dpi: Annotated[
        int,
        typer.Option("--dpi", min=72, max=600, help="Render DPI used before OCR."),
    ] = 220,
    pages: Annotated[
        str | None,
        typer.Option("--pages", help="Page selection, for example: 1-10,15."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Replace the output file if it already exists."),
    ] = False,
    keep_temp: Annotated[
        bool,
        typer.Option("--keep-temp", help="Keep rendered page images for debugging."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Print extra progress details."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    del version
    output_path = output or input_pdf.with_suffix(".md")

    try:
        _validate_paths(input_pdf, output_path, overwrite=overwrite)
        require_openai_key_for_translation(target_lang)
        total_pages = page_count(input_pdf)
        selected_pages = parse_page_range(pages, total_pages)
    except Exception as exc:  # noqa: BLE001 - convert startup failures into CLI messages
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc

    temp_root = Path(tempfile.mkdtemp(prefix="slidebake-"))
    render_dir = temp_root / "pages"

    if verbose:
        console.print(f"PDF pages: {total_pages}; selected: {len(selected_pages)}")
        console.print(f"Temporary directory: {temp_root}")

    try:
        markdown_pages = _process_pages(
            input_pdf=input_pdf,
            selected_pages=selected_pages,
            render_dir=render_dir,
            dpi=dpi,
            target_lang=target_lang,
            bilingual=bilingual,
            model=model,
        )
        content = compose_markdown(
            title=title_from_pdf(input_pdf),
            pages=markdown_pages,
            source_pdf=input_pdf,
            target_lang=target_lang,
            bilingual=bilingual,
        )
        write_markdown(output_path, content, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        if keep_temp:
            console.print(f"Kept temporary files in: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

    console.print(
        f"[green]Wrote[/green] {output_path} "
        f"({len(markdown_pages)} page{'s' if len(markdown_pages) != 1 else ''})"
    )


def _validate_paths(input_pdf: Path, output_path: Path, *, overwrite: bool) -> None:
    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a PDF: {input_pdf}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {output_path}")


def _process_pages(
    *,
    input_pdf: Path,
    selected_pages: list[int],
    render_dir: Path,
    dpi: int,
    target_lang: str | None,
    bilingual: bool,
    model: str | None,
) -> list[MarkdownPage]:
    ocr_runner = OcrRunner()
    translator = (
        OpenAITranslator(target_lang=target_lang, model=model, bilingual=bilingual)
        if target_lang
        else None
    )
    markdown_pages: list[MarkdownPage] = []

    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ]
    with Progress(*progress_columns, console=console) as progress:
        render_task = progress.add_task("Rendering pages", total=1)
        rendered_pages = render_pages(input_pdf, selected_pages, render_dir, dpi=dpi)
        progress.update(render_task, completed=1)

        page_task = progress.add_task("OCR and Markdown", total=len(rendered_pages))
        for rendered in rendered_pages:
            ocr_page = ocr_runner.recognize(rendered.image_path, rendered.page_number)
            raw_text = local_clean_ocr_text(ocr_page)
            if translator:
                translated = translator.translate_page(
                    page_number=rendered.page_number,
                    raw_text=raw_text,
                )
                markdown_pages.append(
                    MarkdownPage(
                        page_number=rendered.page_number,
                        body=translated.body,
                        raw_text=raw_text,
                        error=translated.error,
                    )
                )
            else:
                markdown_pages.append(
                    MarkdownPage(
                        page_number=rendered.page_number,
                        body=raw_text,
                        raw_text=raw_text,
                    )
                )
            progress.advance(page_task)

    return markdown_pages
