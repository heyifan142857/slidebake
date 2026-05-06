from slidebake.ocr import OcrLine, parse_rapidocr_result, sort_lines


def test_parse_rapidocr_result_extracts_boxes() -> None:
    result = [
        ([[10, 20], [30, 20], [30, 40], [10, 40]], "Hello", 0.9),
        ([[0, 0], [1, 0], [1, 1], [0, 1]], "   ", 0.5),
    ]

    lines = parse_rapidocr_result(result)

    assert len(lines) == 1
    assert lines[0].text == "Hello"
    assert lines[0].x0 == 10
    assert lines[0].y1 == 40


def test_sort_lines_uses_top_then_left_order() -> None:
    lines = [
        OcrLine("b", 1, 50, 10, 60, 20),
        OcrLine("c", 1, 0, 30, 10, 40),
        OcrLine("a", 1, 0, 10, 10, 20),
    ]

    assert [line.text for line in sort_lines(lines)] == ["a", "b", "c"]
