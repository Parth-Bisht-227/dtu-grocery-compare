"""Quantity/title normalization and cross-provider SKU matching."""

from matching.matcher import match_products
from matching.normalize import normalize_title, parse_quantity

__all__ = ["match_products", "normalize_title", "parse_quantity"]

