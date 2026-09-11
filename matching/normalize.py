"""Deterministic normalization for messy marketplace text."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from models import NormalizedQuantity


_UNIT_PATTERN = (
    r"kg|kgs?|kilograms?|gms?|grams?|g|"
    r"millilit(?:er|re)s?|ml|lit(?:er|re)s?|ltrs?|ltr|l|"
    r"pieces?|pcs?|counts?|combo(?:s)?"
)
_PREFIX_PACK_RE = re.compile(
    rf"^\s*(?P<count>\d+)\s*[x×]\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s*$",
    re.IGNORECASE,
)
_SUFFIX_PACK_RE = re.compile(
    rf"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s*[x×]\s*(?P<count>\d+)\s*$",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    rf"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s*$",
    re.IGNORECASE,
)
_INLINE_QUANTITY_RE = re.compile(
    rf"\b(?:\d+\s*[x×]\s*)?\d+(?:\.\d+)?\s*(?:{_UNIT_PATTERN})(?:\s*[x×]\s*\d+)?\b",
    re.IGNORECASE,
)
_TOKEN_ALIASES = {
    "minutes": "minute",
    "noodles": "noodle",
    "spices": "spice",
    "chips": "chip",
    "pieces": "piece",
}


def _normalize_unit(value: Decimal, raw_unit: str) -> tuple[Decimal, str]:
    unit = raw_unit.casefold()
    if unit in {"kg", "kgs", "kilogram", "kilograms"}:
        return value * 1000, "g"
    if unit in {"g", "gm", "gms", "gram", "grams"}:
        return value, "g"
    if unit in {"l", "ltr", "ltrs", "liter", "liters", "litre", "litres"}:
        return value * 1000, "ml"
    if unit in {"ml", "milliliter", "milliliters", "millilitre", "millilitres"}:
        return value, "ml"
    if unit in {"pc", "pcs", "piece", "pieces", "count", "counts"}:
        return value, "pcs"
    return value, "combo"


def parse_quantity(raw: str) -> NormalizedQuantity | None:
    """Parse common grocery quantities without guessing unsupported formats."""

    cleaned = unicodedata.normalize("NFKC", raw).strip().replace(",", "")
    match = _PREFIX_PACK_RE.fullmatch(cleaned) or _SUFFIX_PACK_RE.fullmatch(cleaned)
    if match:
        value, unit = _normalize_unit(Decimal(match.group("value")), match.group("unit"))
        return NormalizedQuantity(
            value=value,
            unit=unit,
            pack_count=int(match.group("count")),
            explicit_pack=True,
        )

    match = _SINGLE_RE.fullmatch(cleaned)
    if not match:
        return None
    value, unit = _normalize_unit(Decimal(match.group("value")), match.group("unit"))
    return NormalizedQuantity(value=value, unit=unit)


def normalize_title(title: str) -> str:
    """Normalize formatting while retaining product/variant meaning."""

    text = unicodedata.normalize("NFKC", title).casefold()
    text = text.replace("’", "").replace("'", "")
    text = _INLINE_QUANTITY_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = (_TOKEN_ALIASES.get(token, token) for token in text.split())
    return " ".join(tokens)

