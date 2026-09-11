"""Query relevance ranking, deliberately separate from SKU identity matching."""

from __future__ import annotations

from rapidfuzz import fuzz

from matching.normalize import normalize_title
from models import Product, ProductMatch


def _title_relevance(query: str, title: str) -> float:
    normalized_query = normalize_title(query)
    normalized_title = normalize_title(title)
    if not normalized_query or not normalized_title:
        return 0.0

    # A search query is normally a subset of a full marketplace title. WRatio's
    # subset-friendly behaviour is useful for ranking here, but not for deciding
    # whether two listings are the same SKU.
    return fuzz.WRatio(normalized_query, normalized_title)


def rank_products(query: str, products: list[Product]) -> list[Product]:
    """Return a stable most-relevant-first copy of provider listings."""

    return sorted(
        products,
        key=lambda product: _title_relevance(query, product.title),
        reverse=True,
    )


def rank_matches(query: str, matches: list[ProductMatch]) -> list[ProductMatch]:
    """Rank a comparison by whichever provider title best expresses the query."""

    return sorted(
        matches,
        key=lambda match: max(
            _title_relevance(query, match.blinkit.title),
            _title_relevance(query, match.instamart.title),
        ),
        reverse=True,
    )
