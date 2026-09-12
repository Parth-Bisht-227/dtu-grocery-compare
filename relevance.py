"""Query relevance filtering, deliberately separate from SKU identity matching."""

from __future__ import annotations

from dataclasses import dataclass
from math import log

from rapidfuzz import fuzz

from matching.normalize import extract_quantity, normalize_title
from models import NormalizedQuantity, Product, ProductMatch


MINIMUM_WEIGHTED_COVERAGE = 0.72
FUZZY_TOKEN_THRESHOLD = 85.0


@dataclass(frozen=True)
class RelevanceContext:
    """Query-token evidence inferred from the current marketplace result set."""

    normalized_query: str
    query_tokens: tuple[str, ...]
    token_weights: dict[str, float]
    anchor: str | None
    query_quantity: NormalizedQuantity | None

    @property
    def filters_results(self) -> bool:
        return self.anchor is not None


def _unique_tokens(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(text.split()))


def _token_matches(query_token: str, title_tokens: set[str]) -> bool:
    if query_token in title_tokens:
        return True
    if len(query_token) < 3:
        return False
    return any(
        abs(len(query_token) - len(title_token)) <= 1
        and fuzz.ratio(query_token, title_token) >= FUZZY_TOKEN_THRESHOLD
        for title_token in title_tokens
    )


def build_relevance_context(
    query: str,
    products: list[Product],
) -> RelevanceContext:
    """Infer a distinctive query anchor and bounded IDF-like token weights."""

    normalized_query = normalize_title(query)
    query_tokens = _unique_tokens(normalized_query)
    documents = {
        normalized
        for product in products
        if (normalized := normalize_title(product.title))
    }
    document_tokens = [set(document.split()) for document in documents]
    document_count = len(document_tokens)

    frequencies = {
        token: sum(
            _token_matches(token, title_tokens)
            for title_tokens in document_tokens
        )
        for token in query_tokens
    }
    token_weights = {
        token: 1.0 + log((document_count + 1) / (frequency + 1))
        for token, frequency in frequencies.items()
        if frequency > 0
    }
    anchor = (
        max(
            (token for token in query_tokens if token in token_weights),
            key=token_weights.__getitem__,
        )
        if token_weights
        else None
    )
    return RelevanceContext(
        normalized_query=normalized_query,
        query_tokens=query_tokens,
        token_weights=token_weights,
        anchor=anchor,
        query_quantity=extract_quantity(query),
    )


def _matches_query_quantity(
    requested: NormalizedQuantity | None,
    candidate: NormalizedQuantity | None,
) -> bool:
    """Check search amount only; pack structure belongs to SKU matching."""

    if requested is None:
        return True
    if candidate is None:
        return False
    return (
        requested.unit == candidate.unit
        and requested.total_value == candidate.total_value
    )


def _relevance_evidence(
    context: RelevanceContext,
    titles: tuple[str, ...],
) -> tuple[bool, float]:
    normalized_titles = [normalize_title(title) for title in titles]
    normalized_titles = [title for title in normalized_titles if title]
    if not normalized_titles:
        return False, 0.0

    fuzzy_score = max(
        fuzz.WRatio(context.normalized_query, title)
        for title in normalized_titles
    )
    if not context.filters_results:
        # Some marketplace aliases have no lexical overlap, such as
        # "Coke" -> "Coca-Cola". In that case, preserve the provider's
        # candidates and use fuzzy relevance only for ordering.
        return True, fuzzy_score

    combined_title_tokens = {
        token
        for title in normalized_titles
        for token in title.split()
    }
    matched_tokens = {
        token
        for token in context.token_weights
        if _token_matches(token, combined_title_tokens)
    }
    if context.anchor not in matched_tokens:
        return False, 0.0

    required_token_count = min(2, len(context.token_weights))
    if len(matched_tokens) < required_token_count:
        return False, 0.0

    total_weight = sum(context.token_weights.values())
    matched_weight = sum(context.token_weights[token] for token in matched_tokens)
    weighted_coverage = matched_weight / total_weight
    if weighted_coverage < MINIMUM_WEIGHTED_COVERAGE:
        return False, 0.0

    score = 100 * (0.70 * weighted_coverage + 0.30 * fuzzy_score / 100)
    return True, score


def filter_and_rank_products(
    context: RelevanceContext,
    products: list[Product],
    *,
    enforce_query_quantity: bool = True,
) -> list[Product]:
    """Keep query-eligible listings and return a stable relevance ordering."""

    ranked: list[tuple[int, float, int, Product]] = []
    for index, product in enumerate(products):
        quantity_matches = _matches_query_quantity(
            context.query_quantity,
            product.quantity,
        )
        if enforce_query_quantity and not quantity_matches:
            continue
        accepted, score = _relevance_evidence(context, (product.title,))
        if accepted:
            exact_quantity = int(
                context.query_quantity is not None and quantity_matches
            )
            ranked.append((exact_quantity, score, index, product))
    return [
        product
        for _, _, _, product in sorted(
            ranked,
            key=lambda item: (-item[0], -item[1], item[2]),
        )
    ]


def filter_and_rank_matches(
    context: RelevanceContext,
    matches: list[ProductMatch],
    *,
    enforce_query_quantity: bool = True,
) -> list[ProductMatch]:
    """Keep query-eligible comparisons and return a stable relevance ordering."""

    ranked: list[tuple[int, float, int, ProductMatch]] = []
    for index, match in enumerate(matches):
        quantity_matches = (
            _matches_query_quantity(context.query_quantity, match.blinkit.quantity)
            and _matches_query_quantity(
                context.query_quantity,
                match.instamart.quantity,
            )
        )
        if enforce_query_quantity and not quantity_matches:
            continue
        accepted, score = _relevance_evidence(
            context,
            (match.blinkit.title, match.instamart.title),
        )
        if accepted:
            exact_quantity = int(
                context.query_quantity is not None and quantity_matches
            )
            ranked.append((exact_quantity, score, index, match))
    return [
        match
        for _, _, _, match in sorted(
            ranked,
            key=lambda item: (-item[0], -item[1], item[2]),
        )
    ]
