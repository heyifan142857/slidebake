from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from . import __version__
from .config import OpenAISettings, default_config_path, load_config, resolve_openai_settings
from .markdown import (
    MarkdownPage,
    compose_markdown,
    local_clean_ocr_text,
    title_from_pdf,
    write_markdown,
)
from .ocr import OcrRunner
from .pdf import page_count, parse_page_range, render_pages
from .translate import (
    DEFAULT_MODEL,
    DEFAULT_OPENAI_API,
    OpenAITranslator,
    require_openai_key_for_processing,
)

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
        str | None,
        typer.Argument(
            help="PDF exported from a slide deck.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Markdown output path. Defaults to input.md, or "
                "input_<lang>_<mode>.md for translated output."
            ),
        ),
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
                "SLIDEBAKE_OPENAI_MODEL, config, or gpt-5.4-mini."
            ),
        ),
    ] = None,
    openai_api_key: Annotated[
        str | None,
        typer.Option(
            "--openai-api-key",
            help="OpenAI-compatible API key. Prefer config or environment for daily use.",
        ),
    ] = None,
    openai_base_url: Annotated[
        str | None,
        typer.Option("--openai-base-url", help="OpenAI-compatible base URL."),
    ] = None,
    openai_api: Annotated[
        str | None,
        typer.Option("--openai-api", help="API mode: responses or chat_completions."),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help=f"Config file path. Defaults to {default_config_path()}.",
        ),
    ] = None,
    check_key: Annotated[
        bool,
        typer.Option(
            "--check-key",
            "--checkkey",
            help="Check resolved OpenAI-compatible API settings and exit.",
        ),
    ] = False,
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

    try:
        app_config = load_config(config)
        openai_settings = resolve_openai_settings(
            config=app_config,
            api_key=openai_api_key,
            base_url=openai_base_url,
            model=model,
            api=openai_api,
        )
        if check_key:
            _print_openai_settings(openai_settings)
            raise typer.Exit(0 if openai_settings.api_key else 1)

        if input_pdf is None:
            raise ValueError("Input PDF is required unless --check-key is used.")

        input_pdf_path = _resolve_input_pdf(input_pdf)
        output_path = output or _default_output_path(
            input_pdf_path,
            target_lang=target_lang,
            bilingual=bilingual,
        )
        _validate_paths(input_pdf_path, output_path, overwrite=overwrite)
        require_openai_key_for_processing(api_key=openai_settings.api_key)
        total_pages = page_count(input_pdf_path)
        selected_pages = parse_page_range(pages, total_pages)
    except typer.Exit:
        raise
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
            input_pdf=input_pdf_path,
            selected_pages=selected_pages,
            render_dir=render_dir,
            dpi=dpi,
            target_lang=target_lang,
            bilingual=bilingual,
            openai_settings=openai_settings,
        )
        content = compose_markdown(
            title=title_from_pdf(input_pdf_path),
            pages=markdown_pages,
            source_pdf=input_pdf_path,
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


def _print_openai_settings(settings: OpenAISettings) -> None:
    if settings.api_key:
        console.print("[green]OpenAI-compatible API key found.[/green]")
    else:
        console.print("[red]OpenAI-compatible API key missing.[/red]")
        console.print(
            f"Expected [openai].api_key in {default_config_path()}, or an env/CLI key.",
            markup=False,
        )

    console.print(f"API key: {_mask_secret(settings.api_key)}")
    console.print(f"Base URL: {settings.base_url or '(OpenAI default)'}")
    console.print(f"Model: {settings.model or DEFAULT_MODEL}")
    console.print(f"API mode: {settings.api or DEFAULT_OPENAI_API}")


def _mask_secret(value: str | None) -> str:
    if not value:
        return "(missing)"
    if len(value) <= 8:
        return f"{value[:1]}...{value[-1:]}"
    return f"{value[:4]}...{value[-4:]}"


def _resolve_input_pdf(input_pdf: str) -> Path:
    path = Path(input_pdf)
    if not path.exists():
        raise FileNotFoundError(f"Input PDF not found: {path}")
    if not path.is_file():
        raise ValueError(f"Input must be a file: {path}")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"Input PDF is not readable: {path}")
    return path


def _default_output_path(input_pdf: Path, *, target_lang: str | None, bilingual: bool) -> Path:
    if not target_lang:
        return input_pdf.with_suffix(".md")

    lang = _filename_part(target_lang)
    mode = "bilingual" if bilingual else "translated"
    return input_pdf.with_name(f"{input_pdf.stem}_{lang}_{mode}.md")


def _filename_part(value: str) -> str:
    pieces: list[str] = []
    previous_was_separator = False
    for char in value.strip():
        if char.isalnum() or char in "._-":
            pieces.append(char)
            previous_was_separator = False
        elif not previous_was_separator:
            pieces.append("-")
            previous_was_separator = True

    return "".join(pieces).strip(".-_") or "target"


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
    openai_settings: OpenAISettings,
) -> list[MarkdownPage]:
    ocr_runner = OcrRunner()
    translator = OpenAITranslator(
        target_lang=target_lang,
        model=openai_settings.model,
        api_key=openai_settings.api_key,
        base_url=openai_settings.base_url,
        api=openai_settings.api,
        bilingual=bilingual,
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

        page_task = progress.add_task("OCR, LLM cleanup, and Markdown", total=len(rendered_pages))
        for rendered in rendered_pages:
            ocr_page = ocr_runner.recognize(rendered.image_path, rendered.page_number)
            raw_text = local_clean_ocr_text(ocr_page)
            cleaned = translator.clean_page(
                page_number=rendered.page_number,
                raw_text=raw_text,
            )
            errors = _page_errors(cleanup_error=cleaned.error)
            if target_lang:
                translated = translator.translate_page(
                    page_number=rendered.page_number,
                    raw_text=cleaned.body,
                )
                errors = _page_errors(
                    cleanup_error=cleaned.error,
                    translation_error=translated.error,
                )
                markdown_pages.append(
                    MarkdownPage(
                        page_number=rendered.page_number,
                        body=translated.body,
                        raw_text=raw_text,
                        error=errors,
                    )
                )
            else:
                markdown_pages.append(
                    MarkdownPage(
                        page_number=rendered.page_number,
                        body=cleaned.body,
                        raw_text=raw_text,
                        error=errors,
                    )
                )
            progress.advance(page_task)

    return markdown_pages


def _page_errors(*, cleanup_error: str | None, translation_error: str | None = None) -> str | None:
    errors: list[str] = []
    if cleanup_error:
        errors.append(f"cleanup: {cleanup_error}")
    if translation_error:
        errors.append(f"translation: {translation_error}")
    return "; ".join(errors) or None
