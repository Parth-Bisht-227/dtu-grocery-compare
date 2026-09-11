"""Conservative, deterministic cross-provider SKU matching."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log
from typing import Mapping

from rapidfuzz import fuzz

from matching.normalize import normalize_title
from models import NormalizedQuantity, Product, ProductMatch, Provider


MINIMUM_SCORE = 76.0
AMBIGUITY_MARGIN = 8.0


@dataclass(frozen=True)
class MatchDecision:
    """Pair-level eligibility before list-level mutual-best resolution."""

    accepted: bool
    score: float
    reason: str


def _quantities_compatible(
    left: NormalizedQuantity | None,
    right: NormalizedQuantity | None,
) -> tuple[bool, str]:
    if left is None or right is None:
        return False, "unparsed quantity"
    if left.unit != right.unit:
        return False, "different quantity units"

    left_is_multipack = left.pack_count > 1
    right_is_multipack = right.pack_count > 1
    if left_is_multipack != right_is_multipack:
        return False, "different pack structure"

    if left_is_multipack:
        if left.pack_count != right.pack_count:
            return False, "different pack counts"
        if left.value != right.value:
            return False, "different per-item quantities"
        return True, "equivalent multipack quantity"

    # An explicit 1 x 500 g pack is equivalent to a normal 500 g single pack.
    if left.total_value != right.total_value:
        return False, "different total quantities"
    return True, "equivalent single-pack quantity"


def _quantity_key(quantity: NormalizedQuantity | None) -> tuple[object, ...] | None:
    if quantity is None:
        return None
    if quantity.pack_count <= 1:
        return (quantity.unit, quantity.total_value, 1, False)
    return (quantity.unit, quantity.value, quantity.pack_count, True)


def deduplicate_products(products: list[Product]) -> list[Product]:
    """Remove repeated cards while preserving the provider's original order."""

    seen: set[tuple[object, ...]] = set()
    unique: list[Product] = []
    for product in products:
        if product.provider_product_id:
            identity = (
                "provider-id",
                product.provider,
                product.provider_product_id,
            )
        else:
            identity = (
                "fallback",
                product.provider,
                normalize_title(product.title),
                _quantity_key(product.quantity),
            )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(product)
    return unique


def _token_weights(products: list[Product]) -> dict[str, float]:
    """Compute bounded IDF-like weights from the current deduplicated result set."""

    documents = [set(normalize_title(product.title).split()) for product in products]
    document_count = len(documents)
    frequencies = Counter(token for document in documents for token in document)
    if document_count <= 1:
        return {token: 1.0 for token in frequencies}

    denominator = log(document_count + 1)
    return {
        token: 1
        + 2
        * log((document_count + 1) / (frequency + 1))
        / denominator
        for token, frequency in frequencies.items()
    }


def _title_score(
    left_title: str,
    right_title: str,
    token_weights: Mapping[str, float],
) -> float:
    left_tokens = set(left_title.split())
    right_tokens = set(right_title.split())
    if not left_tokens or not right_tokens:
        return 0.0

    def total_weight(tokens: set[str]) -> float:
        return sum(token_weights.get(token, 1.0) for token in tokens)

    intersection_weight = total_weight(left_tokens & right_tokens)
    left_weight = total_weight(left_tokens)
    right_weight = total_weight(right_tokens)

    # Repeated category words are not extra identity evidence. For example,
    # "Real Fruit Power ... Mixed Fruit Juice" repeats "fruit" because it
    # occurs in both the brand phrase and product description.
    left_unique_title = " ".join(sorted(left_tokens))
    right_unique_title = " ".join(sorted(right_tokens))
    reordered_similarity = (
        fuzz.token_sort_ratio(left_unique_title, right_unique_title) / 100
    )
    weighted_dice = 2 * intersection_weight / (left_weight + right_weight)
    minimum_coverage = min(
        intersection_weight / left_weight,
        intersection_weight / right_weight,
    )
    return round(
        100
        * (
            0.40 * reordered_similarity
            + 0.40 * weighted_dice
            + 0.20 * minimum_coverage
        ),
        2,
    )


def evaluate_match(
    left: Product,
    right: Product,
    *,
    token_weights: Mapping[str, float] | None = None,
) -> MatchDecision:
    """Evaluate one pair; list-level ambiguity is handled by ``match_products``."""

    quantity_ok, quantity_reason = _quantities_compatible(
        left.quantity, right.quantity
    )
    if not quantity_ok:
        return MatchDecision(False, 0.0, quantity_reason)

    left_title = normalize_title(left.title)
    right_title = normalize_title(right.title)
    if not left_title or not right_title:
        return MatchDecision(False, 0.0, "missing normalized title tokens")

    weights = (
        dict(token_weights)
        if token_weights is not None
        else _token_weights([left, right])
    )
    score = _title_score(left_title, right_title, weights)
    if score < MINIMUM_SCORE:
        return MatchDecision(False, score, "title similarity below minimum score")
    return MatchDecision(True, score, quantity_reason)


def _winner(
    candidates: list[tuple[int, float]],
) -> tuple[int, float, float | None] | None:
    """Return index, score, and margin; ``None`` margin means no runner-up."""

    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda candidate: (-candidate[1], candidate[0]))
    best_index, best_score = ranked[0]
    margin = None if len(ranked) == 1 else best_score - ranked[1][1]
    return best_index, best_score, margin


def _margin_is_clear(margin: float | None) -> bool:
    return margin is None or margin >= AMBIGUITY_MARGIN


def match_products(
    blinkit_products: list[Product],
    instamart_products: list[Product],
) -> tuple[list[ProductMatch], dict[Provider, list[Product]]]:
    """Return conservative mutual-best matches and deduplicated unmatched results."""

    blinkit = deduplicate_products(blinkit_products)
    instamart = deduplicate_products(instamart_products)
    weights = _token_weights([*blinkit, *instamart])
    blinkit_titles = [normalize_title(product.title) for product in blinkit]
    instamart_titles = [normalize_title(product.title) for product in instamart]

    blinkit_candidates: list[list[tuple[int, float]]] = [
        [] for _ in blinkit
    ]
    instamart_candidates: list[list[tuple[int, float]]] = [
        [] for _ in instamart
    ]

    for blinkit_index, blinkit_product in enumerate(blinkit):
        for instamart_index, instamart_product in enumerate(instamart):
            quantity_ok, _ = _quantities_compatible(
                blinkit_product.quantity, instamart_product.quantity
            )
            if not quantity_ok:
                continue
            score = _title_score(
                blinkit_titles[blinkit_index],
                instamart_titles[instamart_index],
                weights,
            )
            blinkit_candidates[blinkit_index].append((instamart_index, score))
            instamart_candidates[instamart_index].append((blinkit_index, score))

    blinkit_winners = [_winner(candidates) for candidates in blinkit_candidates]
    instamart_winners = [_winner(candidates) for candidates in instamart_candidates]

    used_blinkit: set[int] = set()
    used_instamart: set[int] = set()
    matches: list[ProductMatch] = []
    for blinkit_index, winner in enumerate(blinkit_winners):
        if winner is None:
            continue
        instamart_index, score, blinkit_margin = winner
        reverse_winner = instamart_winners[instamart_index]
        if reverse_winner is None:
            continue
        reverse_index, _, instamart_margin = reverse_winner
        if reverse_index != blinkit_index:
            continue
        if score < MINIMUM_SCORE:
            continue
        if not _margin_is_clear(blinkit_margin) or not _margin_is_clear(
            instamart_margin
        ):
            continue

        used_blinkit.add(blinkit_index)
        used_instamart.add(instamart_index)
        matches.append(
            ProductMatch(
                blinkit=blinkit[blinkit_index],
                instamart=instamart[instamart_index],
                score=score,
            )
        )

    unmatched = {
        Provider.BLINKIT: [
            product
            for index, product in enumerate(blinkit)
            if index not in used_blinkit
        ],
        Provider.INSTAMART: [
            product
            for index, product in enumerate(instamart)
            if index not in used_instamart
        ],
    }
    return matches, unmatched
