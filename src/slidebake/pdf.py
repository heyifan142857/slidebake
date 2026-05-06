from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    image_path: Path
    width: int
    height: int


def page_count(pdf_path: Path) -> int:
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.page_count


def parse_page_range(spec: str | None, total_pages: int) -> list[int]:
    if total_pages < 1:
        raise ValueError("PDF has no pages.")
    if spec is None or spec.strip() == "":
        return list(range(1, total_pages + 1))

    pages: list[int] = []
    seen: set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"Invalid empty page segment in {spec!r}.")

        if "-" in part:
            start_s, end_s = [piece.strip() for piece in part.split("-", 1)]
            if not start_s or not end_s:
                raise ValueError(f"Invalid page range {part!r}.")
            try:
                start = int(start_s)
                end = int(end_s)
            except ValueError as exc:
                raise ValueError(f"Invalid page range {part!r}.") from exc
            if start > end:
                raise ValueError(f"Invalid descending page range {part!r}.")
            expanded = range(start, end + 1)
        else:
            try:
                expanded = [int(part)]
            except ValueError as exc:
                raise ValueError(f"Invalid page number {part!r}.") from exc

        for page in expanded:
            if page < 1 or page > total_pages:
                raise ValueError(
                    f"Page {page} is outside the valid range 1-{total_pages}."
                )
            if page not in seen:
                pages.append(page)
                seen.add(page)

    return pages


def render_pages(
    pdf_path: Path,
    page_numbers: Iterable[int],
    output_dir: Path,
    *,
    dpi: int,
) -> list[RenderedPage]:
    import fitz

    output_dir.mkdir(parents=True, exist_ok=True)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    rendered: list[RenderedPage] = []

    with fitz.open(pdf_path) as doc:
        for page_number in page_numbers:
            page = doc.load_page(page_number - 1)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = output_dir / f"page-{page_number:04d}.png"
            pix.save(image_path)
            rendered.append(
                RenderedPage(
                    page_number=page_number,
                    image_path=image_path,
                    width=pix.width,
                    height=pix.height,
                )
            )

    return rendered
