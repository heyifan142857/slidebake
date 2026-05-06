import pytest

from slidebake.pdf import parse_page_range


def test_parse_page_range_all_pages_for_empty_spec() -> None:
    assert parse_page_range(None, 3) == [1, 2, 3]
    assert parse_page_range("", 2) == [1, 2]


def test_parse_page_range_mixed_ranges_and_dedupes() -> None:
    assert parse_page_range("1-3, 3, 7", 10) == [1, 2, 3, 7]


@pytest.mark.parametrize("spec", ["3-1", "0", "4", "1,,2", "a", "1-"])
def test_parse_page_range_rejects_invalid_specs(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_page_range(spec, 3)
