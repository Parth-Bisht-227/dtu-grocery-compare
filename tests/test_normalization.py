from decimal import Decimal

import pytest

from matching.normalize import normalize_title, parse_quantity


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


def test_title_normalization_preserves_variant_words_but_removes_formatting():
    assert normalize_title("MAGGI 2-Minute Noodles (71.5 g)") == "maggi 2 minute noodle"

