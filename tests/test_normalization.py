from decimal import Decimal

import pytest

from matching.normalize import extract_quantity, normalize_title, parse_quantity


@pytest.mark.parametrize(
    ("raw", "value", "unit", "pack_count", "total", "explicit_pack"),
    [
        ("280 g", Decimal("280"), "g", 1, Decimal("280"), False),
        ("500gm", Decimal("500"), "g", 1, Decimal("500"), False),
        ("0.5 kg", Decimal("500.0"), "g", 1, Decimal("500.0"), False),
        ("1 kg", Decimal("1000"), "g", 1, Decimal("1000"), False),
        ("72.5 g", Decimal("72.5"), "g", 1, Decimal("72.5"), False),
        ("1L", Decimal("1000"), "ml", 1, Decimal("1000"), False),
        ("4 x 70 g", Decimal("70"), "g", 4, Decimal("280"), True),
        ("71.5 g x 2", Decimal("71.5"), "g", 2, Decimal("143.0"), True),
        ("10 pcs", Decimal("10"), "pcs", 1, Decimal("10"), False),
    ],
)
def test_parse_quantity(raw, value, unit, pack_count, total, explicit_pack):
    quantity = parse_quantity(raw)

    assert quantity is not None
    assert quantity.value == value
    assert quantity.unit == unit
    assert quantity.pack_count == pack_count
    assert quantity.total_value == total
    assert quantity.explicit_pack is explicit_pack


def test_unknown_quantity_is_not_guessed():
    assert parse_quantity("family pack") is None


@pytest.mark.parametrize(
    ("query", "value", "unit", "pack_count", "total"),
    [
        ("Surf Excel Matic Liquid 1L", Decimal("1000"), "ml", 1, Decimal("1000")),
        ("Amul Butter 500 g", Decimal("500"), "g", 1, Decimal("500")),
        ("Dettol Soap 4 x 100 g", Decimal("100"), "g", 4, Decimal("400")),
        ("Eggs 12 pcs", Decimal("12"), "pcs", 1, Decimal("12")),
    ],
)
def test_extract_explicit_query_quantity(query, value, unit, pack_count, total):
    quantity = extract_quantity(query)

    assert quantity is not None
    assert quantity.value == value
    assert quantity.unit == unit
    assert quantity.pack_count == pack_count
    assert quantity.total_value == total


@pytest.mark.parametrize(
    "query",
    [
        "Maggi 2-minute noodles",
        "Nivea Deodorant 48h",
        "Dettol 3X protection",
        "Model X200 version 2",
    ],
)
def test_query_quantity_ignores_unrelated_numbers(query):
    assert extract_quantity(query) is None


def test_ambiguous_query_quantity_is_not_guessed():
    assert extract_quantity("Coca Cola 1L or 2L") is None


def test_title_normalization_preserves_variant_words_but_removes_formatting():
    assert normalize_title("MAGGI 2-Minute Noodles (71.5 g)") == "maggi 2 minute noodle"


def test_title_normalization_removes_only_approved_filler_words():
    assert (
        normalize_title("The Noodles Made With Quality Spices Only")
        == "noodle spice"
    )


def test_title_normalization_preserves_sku_defining_words():
    title = "Original Classic Salted Unsalted Diet Zero Organic Instant Spicy Maxx"

    assert normalize_title(title) == title.casefold()
