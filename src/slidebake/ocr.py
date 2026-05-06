from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    width: int
    height: int
    lines: tuple[OcrLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())


class OcrRunner:
    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    @property
    def engine(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image_path: Path, page_number: int) -> OcrPage:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size

        result, _elapsed = self.engine(str(image_path))
        lines = tuple(sort_lines(parse_rapidocr_result(result)))
        return OcrPage(page_number=page_number, width=width, height=height, lines=lines)


def parse_rapidocr_result(result: Any) -> list[OcrLine]:
    lines: list[OcrLine] = []
    for item in result or []:
        try:
            box, text, score = item[0], str(item[1]).strip(), float(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        lines.append(
            OcrLine(
                text=text,
                score=score,
                x0=min(xs),
                y0=min(ys),
                x1=max(xs),
                y1=max(ys),
            )
        )
    return lines


def sort_lines(lines: list[OcrLine]) -> list[OcrLine]:
    return sorted(lines, key=lambda line: (line.y0, line.x0))
